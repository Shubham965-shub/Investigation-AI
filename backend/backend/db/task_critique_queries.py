"""Queries against generated_content.sql's investigation_task_critique_reports
table. Follows the same conventions as generated_content_queries.py:
UndefinedTableError degrades reads to an empty/false default (this table
shares that file's "not yet run against the live DB" status), any other DB
error propagates.

Keyed by (deviation_id, task_index) — not investigation_rci_sections.id
(2026-08-06, per the user) — see generated_content.sql's table comment for
why: that table isn't populated by anything real right now, since RCI Plan
Creation's own persistence into it also depends on this same file being run.
task_index is the 0-based position of a task within whatever document
services/rci_plan_extraction.py most recently parsed for this investigation.

Only one row per task is ever kept in investigation_task_critique_reports —
each upload replaces it in place (2026-08-06, per the user: no need to retain
previous/rejected attempts' files or critiques). Recommendations live inline
as a JSONB array rather than a child table (see generated_content.sql's
comment). Every attempt's generated recommendation set is still logged
separately, append-only, in investigation_task_critique_recommendation_history
(2026-08-07, per the user) — keyed by (deviation_id, task_index,
attempt_number) — for audit/history purposes only; it is never read by
compute_section_state or any other business rule.
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


async def any_task_critique_started(deviation_id: int) -> bool:
    """Used by rci_plan.py to lock RCI Plan editing once Task Critique has
    begun on any of its tasks."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            return bool(
                await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM investigation_task_critique_reports WHERE deviation_id = $1)",
                    deviation_id,
                )
            )
        except asyncpg.exceptions.UndefinedTableError:
            return False


async def fetch_reports_by_task_index(deviation_id: int) -> Dict[int, Dict[str, Any]]:
    """Returns this investigation's current report per task (only the latest
    attempt is ever stored), keyed by task_index."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                """
                SELECT id, task_index, attempt_number, file_name, is_gospel,
                       summary, task_score, score_breakdown, recommendations, critique_failed, uploaded_at
                FROM investigation_task_critique_reports
                WHERE deviation_id = $1
                """,
                deviation_id,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return {}

        return {
            r["task_index"]: {
                "id": r["id"],
                "attempt_number": r["attempt_number"],
                "file_name": r["file_name"],
                "is_gospel": r["is_gospel"],
                "summary": r["summary"],
                "task_score": r["task_score"],
                "score_breakdown": _parse_score_breakdown(r["score_breakdown"]),
                "critique_failed": r["critique_failed"],
                "uploaded_at": r["uploaded_at"],
                "recommendations": _parse_recommendations(r["recommendations"]),
            }
            for r in rows
        }


async def upsert_report(
    deviation_id: int, task_index: int, attempt_number: int, file_name: str, file_bytes: bytes, is_gospel: bool
) -> int:
    """Replaces this task's report row in place (or creates it on the first
    upload) — critique fields are reset to blank until save_critique fills
    them in again."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO investigation_task_critique_reports
                (deviation_id, task_index, attempt_number, file_name, file_bytes, is_gospel,
                 summary, task_score, score_breakdown, recommendations, critique_failed)
            VALUES ($1, $2, $3, $4, $5, $6, NULL, NULL, NULL, '[]'::jsonb, FALSE)
            ON CONFLICT (deviation_id, task_index) DO UPDATE SET
                attempt_number = EXCLUDED.attempt_number,
                file_name = EXCLUDED.file_name,
                file_bytes = EXCLUDED.file_bytes,
                is_gospel = EXCLUDED.is_gospel,
                summary = NULL,
                task_score = NULL,
                score_breakdown = NULL,
                recommendations = '[]'::jsonb,
                critique_failed = FALSE,
                uploaded_at = now()
            RETURNING id
            """,
            deviation_id,
            task_index,
            attempt_number,
            file_name,
            file_bytes,
            is_gospel,
        )


async def save_critique(report_id: int, summary: Optional[str], task_score: Optional[int], recommendations: List[str]) -> None:
    recs = [
        {"id": i, "description": description, "decision": "pending", "reason": None, "decided_at": None}
        for i, description in enumerate(recommendations)
    ]
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE investigation_task_critique_reports SET summary = $2, task_score = $3, recommendations = $4::jsonb WHERE id = $1",
            report_id,
            summary,
            task_score,
            json.dumps(recs),
        )


async def insert_recommendation_history(
    deviation_id: int, task_index: int, attempt_number: int, summary: Optional[str], recommendations: List[str]
) -> None:
    """Append-only audit log — separate from investigation_task_critique_reports,
    which only ever holds the current attempt (2026-08-07, per the user).
    Not read by any business rule; ON CONFLICT DO NOTHING makes this safe to
    call more than once for the same attempt without erroring."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO investigation_task_critique_recommendation_history
                (deviation_id, task_index, attempt_number, summary, recommendations)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            ON CONFLICT (deviation_id, task_index, attempt_number) DO NOTHING
            """,
            deviation_id,
            task_index,
            attempt_number,
            summary,
            json.dumps(recommendations),
        )


async def fetch_report_file_bytes(report_id: int) -> Optional[bytes]:
    """Used to re-score a report from routers/task_critique.py's decision
    endpoint (2026-08-14) — a report can now become locked/complete purely
    from rejecting every recommendation, with no new upload to score from, so
    the original file's bytes need to be fetched back out for that trigger."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT file_bytes FROM investigation_task_critique_reports WHERE id = $1",
            report_id,
        )


async def set_task_score(report_id: int, task_score: Optional[int], score_breakdown: Optional[List[Dict[str, Any]]] = None) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE investigation_task_critique_reports SET task_score = $2, score_breakdown = $3::jsonb WHERE id = $1",
            report_id,
            task_score,
            json.dumps(score_breakdown) if score_breakdown is not None else None,
        )


async def set_recommendation_decision(deviation_id: int, task_index: int, recommendation_id: int, decision: str, reason: Optional[str]) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, recommendations FROM investigation_task_critique_reports
                WHERE deviation_id = $1 AND task_index = $2 FOR UPDATE
                """,
                deviation_id,
                task_index,
            )
            if row is None:
                return
            recs = _parse_recommendations(row["recommendations"])
            for rec in recs:
                if rec["id"] == recommendation_id:
                    rec["decision"] = decision
                    rec["reason"] = reason
                    rec["decided_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    break
            await conn.execute(
                "UPDATE investigation_task_critique_reports SET recommendations = $2::jsonb WHERE id = $1",
                row["id"],
                json.dumps(recs),
            )


def compute_section_state(report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Thin wrapper — the actual rule lives in db/critique_state.py, shared
    with RC & CAPA Critique's identical business rule."""
    upload_count = report["attempt_number"] if report else 0
    return compute_upload_state(report, upload_count)