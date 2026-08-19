"""Queries against generated_content.sql's investigation_rc_capa_reports
table. Follows the same conventions as task_critique_queries.py:
UndefinedTableError degrades reads to an empty default, any other DB error
propagates.

One row per attempt — never replaced (each upload is a fresh INSERT), so
history across all attempts is naturally preserved, unlike Task Critique's
single upserted row. Each category's summary/strengths/recommendations live
directly on that row as separate rc_*/capa_* columns (2026-08-07, per the
user) — matching Task Critique's "one row, recommendations as an inline
JSONB array" shape — rather than the previous normalized
investigation_rc_capa_critiques/_recommendations child tables. Recommendation
ids are unique per report, not globally: rc's ids run 0..len(rc)-1, capa's
continue numbering from there — see save_critiques/set_recommendation_decision.
"""
from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List, Optional

import asyncpg

from backend.clients.db_client import get_pool
from backend.db.critique_state import compute_upload_state


def _parse_recommendations(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    return raw if isinstance(raw, list) else json.loads(raw)


def _parse_score_breakdown(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    return raw if isinstance(raw, list) else json.loads(raw)


async def fetch_rc_capa_reports(deviation_id: int) -> List[Dict[str, Any]]:
    """Returns all reports for this investigation ordered by attempt_number
    — compute_rc_capa_state below only looks at the last one, but the full
    history is returned so a caller could show it."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                """
                SELECT id, attempt_number, file_name, is_gospel,
                       rc_summary, rc_strengths, rc_recommendations,
                       capa_summary, capa_strengths, capa_recommendations,
                       rc_score, capa_score, total_score, score_breakdown, uploaded_at
                FROM investigation_rc_capa_reports
                WHERE deviation_id = $1 ORDER BY attempt_number
                """,
                deviation_id,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return []

        return [
            {
                "id": r["id"],
                "attempt_number": r["attempt_number"],
                "file_name": r["file_name"],
                "is_gospel": r["is_gospel"],
                "rc_score": r["rc_score"],
                "capa_score": r["capa_score"],
                "total_score": r["total_score"],
                "score_breakdown": _parse_score_breakdown(r["score_breakdown"]),
                "uploaded_at": r["uploaded_at"],
                "critiques": [
                    {
                        "category": "rc_impact",
                        "summary": r["rc_summary"],
                        "strengths": r["rc_strengths"],
                        "recommendations": _parse_recommendations(r["rc_recommendations"]),
                    },
                    {
                        "category": "capa",
                        "summary": r["capa_summary"],
                        "strengths": r["capa_strengths"],
                        "recommendations": _parse_recommendations(r["capa_recommendations"]),
                    },
                ],
            }
            for r in rows
        ]


async def insert_report(
    deviation_id: int, attempt_number: int, file_name: str, file_bytes: bytes, is_gospel: bool
) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO investigation_rc_capa_reports
                (deviation_id, attempt_number, file_name, file_bytes, is_gospel)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            deviation_id,
            attempt_number,
            file_name,
            file_bytes,
            is_gospel,
        )


async def fetch_report_file_bytes(report_id: int) -> Optional[bytes]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT file_bytes FROM investigation_rc_capa_reports WHERE id = $1",
            report_id,
        )


async def save_critiques(
    report_id: int,
    rc_recommendations: List[str],
    rc_strengths: str,
    capa_recommendations: List[str],
    capa_strengths: str,
) -> None:
    """Persists both fixed categories' critique directly onto the report row.
    Neither RCConclusionCritiqueResponse nor CAPACritiqueResponse has a dedicated
    summary field, so both categories' summary is just their strengths string —
    positive-only, matching Task Critique's summary (2026-08-18, per the user).
    rc_summary previously echoed DS's rc_conclusion_text (the investigator's own
    conclusion text, not a critique verdict); that field is no longer persisted.
    Recommendation ids are unique per report: rc's run 0..len(rc)-1, capa's
    continue from there."""
    rc_recs = [
        {"id": i, "description": d, "decision": "pending", "reason": None, "decided_at": None}
        for i, d in enumerate(rc_recommendations)
    ]
    capa_recs = [
        {"id": len(rc_recs) + i, "description": d, "decision": "pending", "reason": None, "decided_at": None}
        for i, d in enumerate(capa_recommendations)
    ]
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE investigation_rc_capa_reports SET
                rc_summary = $2, rc_strengths = $3, rc_recommendations = $4::jsonb,
                capa_summary = $5, capa_strengths = $6, capa_recommendations = $7::jsonb
            WHERE id = $1
            """,
            report_id,
            rc_strengths,
            rc_strengths,
            json.dumps(rc_recs),
            capa_strengths,
            capa_strengths,
            json.dumps(capa_recs),
        )


async def set_rc_capa_scores(
    report_id: int,
    rc_score: Optional[int],
    capa_score: Optional[int],
    total_score: Optional[int],
    score_breakdown: Optional[List[Dict[str, Any]]] = None,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE investigation_rc_capa_reports SET rc_score = $2, capa_score = $3, total_score = $4, score_breakdown = $5::jsonb WHERE id = $1",
            report_id,
            rc_score,
            capa_score,
            total_score,
            json.dumps(score_breakdown) if score_breakdown is not None else None,
        )


async def set_recommendation_decision(report_id: int, recommendation_id: int, decision: str, reason: Optional[str]) -> None:
    """recommendation_id is only unique within one report (see save_critiques)
    — determine which category's array actually contains it, then rewrite
    that array with the matching element's decision updated."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT rc_recommendations, capa_recommendations FROM investigation_rc_capa_reports WHERE id = $1 FOR UPDATE",
                report_id,
            )
            if row is None:
                return
            decided_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            for column in ("rc_recommendations", "capa_recommendations"):
                recs = _parse_recommendations(row[column])
                matched = False
                for rec in recs:
                    if rec["id"] == recommendation_id:
                        rec["decision"] = decision
                        rec["reason"] = reason
                        rec["decided_at"] = decided_at
                        matched = True
                        break
                if matched:
                    await conn.execute(
                        f"UPDATE investigation_rc_capa_reports SET {column} = $2::jsonb WHERE id = $1",
                        report_id,
                        json.dumps(recs),
                    )
                    return


def compute_rc_capa_state(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Thin wrapper around the shared state machine — flattens the latest
    report's two categories' recommendation lists into one before delegating,
    since compute_upload_state doesn't know or care about categories."""
    if not reports:
        return compute_upload_state(None, 0)
    latest = reports[-1]
    flattened_latest = {
        **latest,
        "recommendations": [rec for critique in latest["critiques"] for rec in critique["recommendations"]],
    }
    return compute_upload_state(flattened_latest, len(reports))