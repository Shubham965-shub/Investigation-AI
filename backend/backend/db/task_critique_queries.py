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


def _parse_task_findings(raw: Any) -> List[Dict[str, Any]]:
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
                       summary, task_score, score_breakdown, recommendations, task_findings,
                       critique_failed, uploaded_at
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
                "task_findings": _parse_task_findings(r["task_findings"]),
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
                 summary, task_score, score_breakdown, recommendations, task_findings, critique_failed)
            VALUES ($1, $2, $3, $4, $5, $6, NULL, NULL, NULL, '[]'::jsonb, '[]'::jsonb, FALSE)
            ON CONFLICT (deviation_id, task_index) DO UPDATE SET
                attempt_number = EXCLUDED.attempt_number,
                file_name = EXCLUDED.file_name,
                file_bytes = EXCLUDED.file_bytes,
                is_gospel = EXCLUDED.is_gospel,
                summary = NULL,
                task_score = NULL,
                score_breakdown = NULL,
                recommendations = '[]'::jsonb,
                task_findings = '[]'::jsonb,
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


async def save_critique(
    report_id: int,
    summary: Optional[str],
    task_score: Optional[int],
    recommendations: List[str],
    task_findings: Optional[List[Dict[str, Any]]] = None,
) -> None:
    recs = _build_recommendation_records(recommendations)
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE investigation_task_critique_reports SET summary = $2, task_score = $3, "
            "recommendations = $4::jsonb, task_findings = $5::jsonb WHERE id = $1",
            report_id,
            summary,
            task_score,
            json.dumps(recs),
            json.dumps(task_findings or []),
        )


def _build_recommendation_records(recommendations: List[str]) -> List[Dict[str, Any]]:
    """Same {id, description, decision, reason, decided_at} shape save_critique
    puts on the live report row — ids assigned identically (enumerate order),
    so a decision made on the live report and the matching history row for
    that same attempt stay correlated by id."""
    return [
        {"id": i, "description": description, "decision": "pending", "reason": None, "decided_at": None}
        for i, description in enumerate(recommendations)
    ]


async def insert_recommendation_history(
    deviation_id: int, task_index: int, attempt_number: int, summary: Optional[str], recommendations: List[str]
) -> None:
    """Append-only audit log — separate from investigation_task_critique_reports,
    which only ever holds the current attempt (2026-08-07, per the user).
    Stores the same rich {id, description, decision, reason} shape as the live
    report (2026-08-18, per the user: accept/reject/reason needs to survive
    here too) — set_recommendation_decision keeps this row's copy in sync as
    decisions are made on the current attempt, so by the time a new upload
    supersedes it, this row already reflects its final decided state.
    ON CONFLICT DO NOTHING makes this safe to call more than once for the
    same attempt without erroring (or clobbering decisions already recorded
    here by set_recommendation_decision)."""
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
            json.dumps(_build_recommendation_records(recommendations)),
        )


async def fetch_recommendation_history(deviation_id: int, task_index: int) -> List[Dict[str, Any]]:
    """The full audit trail across every attempt for this task — unlike
    investigation_task_critique_reports (which only ever holds the current
    attempt, replaced in place), this table is append-only, so it's the only
    place a prior attempt's recommendations survive being superseded.
    Deliberately independent of lock/complete state — the whole point is
    that this stays visible even once the task is scored and done
    (2026-08-18, per the user). Newest attempt first — the current/live
    attempt is already the highest number and shown separately above this
    list, so this history reads in reverse-chronological order underneath it."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                """
                SELECT attempt_number, summary, recommendations, created_at
                FROM investigation_task_critique_recommendation_history
                WHERE deviation_id = $1 AND task_index = $2
                ORDER BY attempt_number DESC
                """,
                deviation_id,
                task_index,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return []
        return [
            {
                "attempt_number": r["attempt_number"],
                "summary": r["summary"],
                # Same {id, description, decision, reason, decided_at} shape as
                # the live report — set_recommendation_decision keeps this in
                # sync as decisions are made (2026-08-18, per the user).
                "recommendations": _parse_recommendations(r["recommendations"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]


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


async def set_task_score(
    report_id: int,
    task_score: Optional[int],
    score_breakdown: Optional[List[Dict[str, Any]]] = None,
    critique_failed: bool = False,
) -> None:
    """critique_failed=True means the scoring call ran but did not produce a
    score (DS scoring failure, or no Task Report section detected) — lets the
    frontend distinguish that from "not scored yet", which otherwise both show
    task_score = NULL (ticket 500954)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE investigation_task_critique_reports SET task_score = $2, score_breakdown = $3::jsonb, critique_failed = $4 WHERE id = $1",
            report_id,
            task_score,
            json.dumps(score_breakdown) if score_breakdown is not None else None,
            critique_failed,
        )


async def set_recommendation_decision(deviation_id: int, task_index: int, recommendation_id: int, decision: str, reason: Optional[str]) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, attempt_number, recommendations FROM investigation_task_critique_reports
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
            # Keep the audit-log row for this same attempt in sync too
            # (2026-08-18, per the user: accept/reject/reason needs to survive
            # in the history even after this attempt is superseded by a new
            # upload, since investigation_task_critique_reports only ever
            # holds the current attempt).
            await conn.execute(
                """
                UPDATE investigation_task_critique_recommendation_history
                SET recommendations = $4::jsonb
                WHERE deviation_id = $1 AND task_index = $2 AND attempt_number = $3
                """,
                deviation_id,
                task_index,
                row["attempt_number"],
                json.dumps(recs),
            )


def compute_section_state(report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Thin wrapper — the actual rule lives in db/critique_state.py, shared
    with RC & CAPA Critique's identical business rule."""
    upload_count = report["attempt_number"] if report else 0
    return compute_upload_state(report, upload_count)