"""Queries against generated_content.sql's investigation_rc_capa_reports/
critiques/recommendations tables. Follows the same conventions as
task_critique_queries.py: UndefinedTableError degrades reads to an empty
default, any other DB error propagates.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import asyncpg

from backend.clients.db_client import get_pool
from backend.db.critique_state import compute_upload_state


async def fetch_rc_capa_reports(deviation_id: int) -> List[Dict[str, Any]]:
    """Returns all reports for this investigation ordered by attempt_number,
    each with its two critiques (categories) and each critique's
    recommendations — compute_rc_capa_state below only looks at the last
    report, but the full history is returned so a caller could show it."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            report_rows = await conn.fetch(
                """
                SELECT id, attempt_number, file_name, is_gospel, rc_score, capa_score, total_score, uploaded_at
                FROM investigation_rc_capa_reports
                WHERE deviation_id = $1 ORDER BY attempt_number
                """,
                deviation_id,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return []
        if not report_rows:
            return []

        report_ids = [r["id"] for r in report_rows]
        try:
            critique_rows = await conn.fetch(
                """
                SELECT id, report_id, category, summary, strengths
                FROM investigation_rc_capa_critiques
                WHERE report_id = ANY($1::int[]) ORDER BY report_id, id
                """,
                report_ids,
            )
        except asyncpg.exceptions.UndefinedTableError:
            critique_rows = []

        critique_ids = [r["id"] for r in critique_rows]
        recs_by_critique: Dict[int, List[Dict[str, Any]]] = {}
        if critique_ids:
            try:
                rec_rows = await conn.fetch(
                    """
                    SELECT id, critique_id, description, decision, reason
                    FROM investigation_rc_capa_recommendations
                    WHERE critique_id = ANY($1::int[]) ORDER BY critique_id, sort_order, id
                    """,
                    critique_ids,
                )
            except asyncpg.exceptions.UndefinedTableError:
                rec_rows = []
            for r in rec_rows:
                recs_by_critique.setdefault(r["critique_id"], []).append(
                    {
                        "id": r["id"],
                        "description": r["description"],
                        "decision": r["decision"],
                        "reason": r["reason"],
                    }
                )

        critiques_by_report: Dict[int, List[Dict[str, Any]]] = {}
        for c in critique_rows:
            critiques_by_report.setdefault(c["report_id"], []).append(
                {
                    "category": c["category"],
                    "summary": c["summary"],
                    "strengths": c["strengths"],
                    "recommendations": recs_by_critique.get(c["id"], []),
                }
            )

        return [
            {
                "id": r["id"],
                "attempt_number": r["attempt_number"],
                "file_name": r["file_name"],
                "is_gospel": r["is_gospel"],
                "rc_score": r["rc_score"],
                "capa_score": r["capa_score"],
                "total_score": r["total_score"],
                "uploaded_at": r["uploaded_at"],
                "critiques": critiques_by_report.get(r["id"], []),
            }
            for r in report_rows
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
    rc_conclusion_text: str,
    rc_recommendations: List[str],
    rc_strengths: str,
    capa_recommendations: List[str],
    capa_strengths: str,
) -> None:
    """Persists both fixed categories' critique + recommendation rows for one
    report, in a single transaction. rc_impact's summary is DS's
    rc_conclusion_text; capa has no dedicated summary field in DS's response
    (CAPACritiqueResponse), so its summary falls back to strengths."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            rc_critique_id = await conn.fetchval(
                """
                INSERT INTO investigation_rc_capa_critiques (report_id, category, summary, strengths)
                VALUES ($1, 'rc_impact', $2, $3)
                RETURNING id
                """,
                report_id,
                rc_conclusion_text,
                rc_strengths,
            )
            if rc_recommendations:
                await conn.executemany(
                    """
                    INSERT INTO investigation_rc_capa_recommendations (critique_id, description, sort_order)
                    VALUES ($1, $2, $3)
                    """,
                    [(rc_critique_id, description, i) for i, description in enumerate(rc_recommendations)],
                )

            capa_critique_id = await conn.fetchval(
                """
                INSERT INTO investigation_rc_capa_critiques (report_id, category, summary, strengths)
                VALUES ($1, 'capa', $2, $3)
                RETURNING id
                """,
                report_id,
                capa_strengths,
                capa_strengths,
            )
            if capa_recommendations:
                await conn.executemany(
                    """
                    INSERT INTO investigation_rc_capa_recommendations (critique_id, description, sort_order)
                    VALUES ($1, $2, $3)
                    """,
                    [(capa_critique_id, description, i) for i, description in enumerate(capa_recommendations)],
                )


async def set_rc_capa_scores(
    report_id: int, rc_score: Optional[int], capa_score: Optional[int], total_score: Optional[int]
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE investigation_rc_capa_reports SET rc_score = $2, capa_score = $3, total_score = $4 WHERE id = $1",
            report_id,
            rc_score,
            capa_score,
            total_score,
        )


async def set_recommendation_decision(recommendation_id: int, decision: str, reason: Optional[str]) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE investigation_rc_capa_recommendations
            SET decision = $2, reason = $3, decided_at = now()
            WHERE id = $1
            """,
            recommendation_id,
            decision,
            reason,
        )


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