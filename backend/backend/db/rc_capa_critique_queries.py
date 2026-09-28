"""Queries against generated_content.sql's investigation_rc_capa_reports.
Follows task_critique_queries.py's conventions (UndefinedTableError degrades
reads to empty, other errors propagate). One row per attempt — never
replaced, so history is naturally preserved, unlike Task Critique's single
upserted row. Recommendation ids are unique per report, not globally: rc runs
0..len(rc)-1, capa continues from there.
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


def _parse_capa_items(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    return raw if isinstance(raw, list) else json.loads(raw)


async def fetch_rc_capa_reports(deviation_id: int, rci_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """All reports for this investigation, ordered by attempt_number
    (compute_rc_capa_state only looks at the last one)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                """
                SELECT id, attempt_number, file_name, is_gospel,
                       rc_summary, rc_recommendations,
                       capa_summary, capa_recommendations,
                       rc_score, impact_score, capa_score, total_score, score_breakdown, uploaded_at,
                       rc_conclusion_text_raw, is_repeat_occurrence, impact_assessment_text,
                       impact_conclusion_text, correction_remedial_text, capa_text_raw, capa_items,
                       critique_pending, critique_failed
                FROM investigation_rc_capa_reports
                WHERE deviation_id = $1 AND rci_id IS NOT DISTINCT FROM $2 ORDER BY attempt_number
                """,
                deviation_id,
                rci_id,
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
                "critique_pending": r["critique_pending"],
                "critique_failed": r["critique_failed"],
                "uploaded_at": r["uploaded_at"],
                "critiques": [
                    {
                        "category": "rc_impact",
                        "summary": r["rc_summary"],
                        "recommendations": _parse_recommendations(r["rc_recommendations"]),
                        # The report's own extracted content, not part of RcCapaCritique's
                        # public schema (extra keys ignored there) — consumed only by RCI
                        # Report generation, which reads this dict directly.
                        "rc_conclusion_text_raw": r["rc_conclusion_text_raw"],
                        "is_repeat_occurrence": r["is_repeat_occurrence"],
                        "impact_assessment_text": r["impact_assessment_text"],
                        "impact_conclusion_text": r["impact_conclusion_text"],
                    },
                    {
                        "category": "capa",
                        "summary": r["capa_summary"],
                        "recommendations": _parse_recommendations(r["capa_recommendations"]),
                        "capa_text_raw": r["capa_text_raw"],
                        "capa_items": _parse_capa_items(r["capa_items"]),
                        "correction_remedial_text": r["correction_remedial_text"],
                    },
                ],
            }
            for r in rows
        ]


async def insert_report(
    deviation_id: int,
    attempt_number: int,
    file_name: str,
    file_bytes: bytes,
    is_gospel: bool,
    rci_id: Optional[str] = None,
    uploaded_by: Optional[int] = None,
    critique_pending: bool = False,
) -> int:
    """critique_pending=True is the normal case now (see
    routers/rc_capa_critique.py's upload_rc_capa_report): the row is persisted
    before DS's critique/scoring calls run in the background, and cleared via
    clear_critique_pending once they finish — mirrors task_critique_queries.py's
    upsert_report."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO investigation_rc_capa_reports
                (deviation_id, rci_id, attempt_number, file_name, file_bytes, is_gospel, uploaded_by, critique_pending)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            deviation_id,
            rci_id,
            attempt_number,
            file_name,
            file_bytes,
            is_gospel,
            uploaded_by,
            critique_pending,
        )


async def clear_critique_pending(report_id: int) -> None:
    """Called as the very last step of background upload processing (routers/rc_capa_critique.py's
    _process_rc_capa_report_async), regardless of which path it took (critique-only, critique+score,
    gospel+score, or a DS failure) — single place marking "background processing is done". Mirrors
    task_critique_queries.py's clear_critique_pending."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE investigation_rc_capa_reports SET critique_pending = FALSE WHERE id = $1",
            report_id,
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
    rc_conclusion_text_raw: str = "",
    is_repeat_occurrence: Optional[bool] = None,
    impact_assessment_text: str = "",
    impact_conclusion_text: str = "",
    correction_remedial_text: str = "",
    capa_text_raw: str = "",
    capa_items: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Persists both categories' critique onto the report row. Summaries are
    extracted via plain docx parsing (no LLM) then condensed to a few
    sentences for the dashboard card — condensation can't add facts, so this
    is still not an independent critique verdict (rc_strengths/capa_strengths
    columns still exist but are no longer written/read). Recommendation ids
    run rc, then impact, then capa; each rc/impact one is tagged accordingly
    so the frontend can split them into subsections. The raw
    rc_conclusion_text_raw/impact_*/capa_text_raw/capa_items fields carry the
    same extraction's raw content alongside the condensed summaries, for RCI
    Report generation."""
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
                capa_summary = $4, capa_recommendations = $5::jsonb,
                rc_conclusion_text_raw = $6, is_repeat_occurrence = $7,
                impact_assessment_text = $8, correction_remedial_text = $9,
                capa_text_raw = $10, capa_items = $11::jsonb, impact_conclusion_text = $12
            WHERE id = $1
            """,
            report_id,
            rc_summary,
            json.dumps(rc_recs),
            capa_summary,
            json.dumps(capa_recs),
            rc_conclusion_text_raw,
            is_repeat_occurrence,
            impact_assessment_text,
            correction_remedial_text,
            capa_text_raw,
            json.dumps(capa_items or []),
            impact_conclusion_text,
        )


async def set_rc_capa_scores(
    report_id: int,
    rc_score: Optional[int],
    impact_score: Optional[int],
    capa_score: Optional[int],
    total_score: Optional[int],
    score_breakdown: Optional[List[Dict[str, Any]]] = None,
    critique_failed: bool = False,
) -> None:
    """critique_failed=True means the background critique/scoring calls ran but did not produce a
    real result (DS failure, or scoring incomplete) — mirrors task_critique_queries.py's
    set_task_score. Lets compute_upload_state (db/critique_state.py) distinguish this from "DS
    genuinely found nothing to flag", so a transient DS failure doesn't permanently lock the
    report with no reupload allowed."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE investigation_rc_capa_reports SET rc_score = $2, impact_score = $3, capa_score = $4, total_score = $5, score_breakdown = $6::jsonb, critique_failed = $7 WHERE id = $1",
            report_id,
            rc_score,
            impact_score,
            capa_score,
            total_score,
            json.dumps(score_breakdown) if score_breakdown is not None else None,
            critique_failed,
        )


async def set_recommendation_decision(report_id: int, recommendation_id: int, decision: str, reason: Optional[str]) -> None:
    """recommendation_id is unique only within one report — find which
    category's array contains it, then rewrite that array."""
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
    """Flattens the latest report's two categories into one list before
    delegating to the shared state machine."""
    if not reports:
        return compute_upload_state(None, 0)
    latest = reports[-1]
    flattened_latest = {
        **latest,
        "recommendations": [rec for critique in latest["critiques"] for rec in critique["recommendations"]],
    }
    return compute_upload_state(flattened_latest, len(reports))