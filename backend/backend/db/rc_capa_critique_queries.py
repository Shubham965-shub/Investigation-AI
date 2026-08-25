"""Queries against generated_content.sql's investigation_rc_capa_reports
table. Follows the same conventions as task_critique_queries.py:
UndefinedTableError degrades reads to an empty default, any other DB error
propagates.

One row per attempt — never replaced (each upload is a fresh INSERT), so
history across all attempts is naturally preserved, unlike Task Critique's
single upserted row. Each category's summary/recommendations live
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
                       rc_summary, rc_recommendations,
                       capa_summary, capa_recommendations,
                       rc_score, impact_score, capa_score, total_score, score_breakdown, uploaded_at
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
                "impact_score": r["impact_score"],
                "capa_score": r["capa_score"],
                "total_score": r["total_score"],
                "score_breakdown": _parse_score_breakdown(r["score_breakdown"]),
                "uploaded_at": r["uploaded_at"],
                "critiques": [
                    {
                        "category": "rc_impact",
                        "summary": r["rc_summary"],
                        "recommendations": _parse_recommendations(r["rc_recommendations"]),
                    },
                    {
                        "category": "capa",
                        "summary": r["capa_summary"],
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
    impact_recommendations: List[str],
    rc_summary: str,
    capa_recommendations: List[str],
    capa_summary: str,
) -> None:
    """Persists both fixed categories' critique directly onto the report row.
    `rc_summary`/`capa_summary` are sourced from the report's own RC Conclusion / CAPA section
    text, pulled by ds via plain docx parsing (extract_rci_report_sections, no LLM), then
    condensed by ds to 3-4 plain-language sentences since the full verbatim section is too
    long for a dashboard summary card (2026-08-20, per the user) — the condensation step is
    forbidden from adding any fact not already in the extracted text, so this is still not a
    critique verdict or an LLM's independent judgment of the report. No separate LLM
    "strengths" verdict is generated or persisted anymore (2026-08-20, per the user — the
    rc_strengths/capa_strengths columns still exist on the table but are no longer written or
    read).
    Recommendation ids are unique per report: rc_recommendations run
    0..len(rc)-1, impact_recommendations continue from there, then capa's.
    Each rc_impact recommendation is tagged "rc" or "impact" (2026-08-24, per
    the user) so the frontend can render the two as separate subsections;
    capa's own recommendations carry no type (not split this way)."""
    rc_recs = [
        {"id": i, "description": d, "type": "rc", "decision": "pending", "reason": None, "decided_at": None}
        for i, d in enumerate(rc_recommendations)
    ] + [
        {"id": len(rc_recommendations) + i, "description": d, "type": "impact", "decision": "pending", "reason": None, "decided_at": None}
        for i, d in enumerate(impact_recommendations)
    ]
    capa_recs = [
        {"id": len(rc_recs) + i, "description": d, "type": None, "decision": "pending", "reason": None, "decided_at": None}
        for i, d in enumerate(capa_recommendations)
    ]
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE investigation_rc_capa_reports SET
                rc_summary = $2, rc_recommendations = $3::jsonb,
                capa_summary = $4, capa_recommendations = $5::jsonb
            WHERE id = $1
            """,
            report_id,
            rc_summary,
            json.dumps(rc_recs),
            capa_summary,
            json.dumps(capa_recs),
        )


async def set_rc_capa_scores(
    report_id: int,
    rc_score: Optional[int],
    impact_score: Optional[int],
    capa_score: Optional[int],
    total_score: Optional[int],
    score_breakdown: Optional[List[Dict[str, Any]]] = None,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE investigation_rc_capa_reports SET rc_score = $2, impact_score = $3, capa_score = $4, total_score = $5, score_breakdown = $6::jsonb WHERE id = $1",
            report_id,
            rc_score,
            impact_score,
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