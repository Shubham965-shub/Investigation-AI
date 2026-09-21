"""Queries against generated_content.sql's tables. Reads catch
UndefinedTableError specifically and degrade to the same "nothing generated
yet" default as a missing row — the table not existing yet is an expected
pre-approval state, not an anomaly. Other DB errors still propagate.
"""
from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List, Optional

import asyncpg

from backend.clients.db_client import get_pool


def _parse_date(value: Any) -> Optional[datetime.date]:
    """asyncpg requires a real datetime.date for this column, not the
    "YYYY-MM-DD" string the frontend sends — passing the raw string through
    fails with "'str' object has no attribute 'toordinal'"."""
    if not value:
        return None
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(value)


async def fetch_problem_statement(deviation_id: int) -> Optional[str]:
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT problem_statement FROM investigation_problem_statements WHERE deviation_id = $1",
                deviation_id,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return None
        return row["problem_statement"] if row else None


# None = no row yet (never generated); [] is a real "generated, nothing meaningful found" result.
async def fetch_problem_statement_enhancements(deviation_id: int) -> Optional[List[Dict[str, Any]]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT enhancements FROM investigation_problem_statement_enhancements WHERE deviation_id = $1",
                deviation_id,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return None
        if row is None:
            return None
        raw = row["enhancements"]
        return raw if isinstance(raw, list) else json.loads(raw)


async def save_problem_statement_enhancements(deviation_id: int, enhancements: List[Dict[str, Any]]) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO investigation_problem_statement_enhancements (deviation_id, enhancements, generated_at)
            VALUES ($1, $2, now())
            ON CONFLICT (deviation_id) DO UPDATE
                SET enhancements = EXCLUDED.enhancements, generated_at = now()
            """,
            deviation_id,
            json.dumps(enhancements),
        )


# Called when the problem statement is manually edited — the persisted enhancements diff was
# computed against the pre-edit text and would otherwise silently go stale.
async def delete_problem_statement_enhancements(deviation_id: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "DELETE FROM investigation_problem_statement_enhancements WHERE deviation_id = $1", deviation_id
            )
        except asyncpg.exceptions.UndefinedTableError:
            pass


async def fetch_evidence_items(deviation_id: int) -> List[Dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                """
                SELECT description, is_checked FROM investigation_evidence_items
                WHERE deviation_id = $1 ORDER BY sort_order, id
                """,
                deviation_id,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return []
        return [{"description": r["description"], "is_checked": r["is_checked"]} for r in rows]


async def fetch_questionnaire_items(deviation_id: int) -> List[Dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                """
                SELECT description, is_checked FROM investigation_questionnaire_items
                WHERE deviation_id = $1 ORDER BY sort_order, id
                """,
                deviation_id,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return []
        return [{"description": r["description"], "is_checked": r["is_checked"]} for r in rows]


async def fetch_rci_sections(deviation_id: int) -> List[Dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            section_rows = await conn.fetch(
                """
                SELECT id, title, correlation, due_date, assignee, is_checked
                FROM investigation_rci_sections
                WHERE deviation_id = $1 ORDER BY sort_order, id
                """,
                deviation_id,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return []
        if not section_rows:
            return []

        section_ids = [r["id"] for r in section_rows]
        task_rows = await conn.fetch(
            """
            SELECT section_id, description, is_checked FROM investigation_rci_tasks
            WHERE section_id = ANY($1::int[]) ORDER BY sort_order, id
            """,
            section_ids,
        )
        tasks_by_section: Dict[int, List[Dict[str, Any]]] = {}
        for t in task_rows:
            tasks_by_section.setdefault(t["section_id"], []).append(
                {"description": t["description"], "is_checked": t["is_checked"]}
            )

        return [
            {
                "id": s["id"],
                "title": s["title"],
                "correlation": s["correlation"],
                "due_date": s["due_date"].isoformat() if s["due_date"] else None,
                "assignee": s["assignee"],
                "is_checked": s["is_checked"],
                "tasks": tasks_by_section.get(s["id"], []),
            }
            for s in section_rows
        ]


# Keyed by (deviation_id, rci_id), not deviation_id alone — a deviation with
# multiple RCI IDs renders as multiple rows, each with its own remark. Empty
# rci_id is normalized to SQL NULL to match the NULLS NOT DISTINCT key so
# "no rci_id" still upserts onto one row instead of a new one every save.
async def fetch_remarks(deviation_ids: List[int]) -> Dict[int, Dict[str, str]]:
    if not deviation_ids:
        return {}
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                "SELECT deviation_id, rci_id, remark FROM investigation_remarks WHERE deviation_id = ANY($1::int[])",
                deviation_ids,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return {}
    result: Dict[int, Dict[str, str]] = {}
    for r in rows:
        result.setdefault(r["deviation_id"], {})[r["rci_id"] or ""] = r["remark"]
    return result


async def save_remark(deviation_id: int, rci_id: str, remark: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO investigation_remarks (deviation_id, rci_id, remark, updated_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (deviation_id, rci_id) DO UPDATE
                SET remark = EXCLUDED.remark, updated_at = now()
            """,
            deviation_id,
            rci_id or None,
            remark,
        )


async def save_problem_statement(deviation_id: int, problem_statement: str, generated_by: Optional[int] = None) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO investigation_problem_statements (deviation_id, problem_statement, generated_at, generated_by)
            VALUES ($1, $2, now(), $3)
            ON CONFLICT (deviation_id) DO UPDATE
                SET problem_statement = EXCLUDED.problem_statement, generated_at = now(), generated_by = EXCLUDED.generated_by
            """,
            deviation_id,
            problem_statement,
            generated_by,
        )


async def replace_evidence_items(deviation_id: int, items: List[Dict[str, Any]], generated_by: Optional[int] = None) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Same DELETE-then-INSERT race as replace_rci_sections — needs the same lock.
            await conn.execute("SELECT pg_advisory_xact_lock($1)", deviation_id)
            await conn.execute("DELETE FROM investigation_evidence_items WHERE deviation_id = $1", deviation_id)
            if items:
                await conn.executemany(
                    """
                    INSERT INTO investigation_evidence_items (deviation_id, description, is_checked, sort_order, generated_by)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    [
                        (deviation_id, item["description"], item.get("is_checked", True), i, generated_by)
                        for i, item in enumerate(items)
                    ],
                )


async def replace_questionnaire_items(deviation_id: int, items: List[Dict[str, Any]], generated_by: Optional[int] = None) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Same DELETE-then-INSERT race as replace_rci_sections — needs the same lock.
            await conn.execute("SELECT pg_advisory_xact_lock($1)", deviation_id)
            await conn.execute("DELETE FROM investigation_questionnaire_items WHERE deviation_id = $1", deviation_id)
            if items:
                await conn.executemany(
                    """
                    INSERT INTO investigation_questionnaire_items (deviation_id, description, is_checked, sort_order, generated_by)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    [
                        (deviation_id, item["description"], item.get("is_checked", True), i, generated_by)
                        for i, item in enumerate(items)
                    ],
                )


async def replace_rci_sections(deviation_id: int, sections: List[Dict[str, Any]], generated_by: Optional[int] = None) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Serializes concurrent replace calls for the same investigation
            # (e.g. double-clicked Generate + assignee-edit PUTs) — without
            # it, overlapping DELETE-then-INSERT sequences can each miss the
            # other's uncommitted DELETE and duplicate every section
            # (confirmed live: one deviation_id got 6 sections x 8 duplicate
            # copies). Transaction-scoped, auto-released on commit/rollback.
            await conn.execute("SELECT pg_advisory_xact_lock($1)", deviation_id)
            # ON DELETE CASCADE on investigation_rci_tasks.section_id takes care of tasks.
            await conn.execute("DELETE FROM investigation_rci_sections WHERE deviation_id = $1", deviation_id)
            for i, section in enumerate(sections):
                section_id = await conn.fetchval(
                    """
                    INSERT INTO investigation_rci_sections
                        (deviation_id, title, correlation, due_date, assignee, sort_order, is_checked, generated_by)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                    """,
                    deviation_id,
                    section["title"],
                    section.get("correlation"),
                    _parse_date(section.get("due_date")),
                    section.get("assignee"),
                    i,
                    section.get("is_checked", True),
                    generated_by,
                )
                tasks = section.get("tasks") or []
                if tasks:
                    await conn.executemany(
                        """
                        INSERT INTO investigation_rci_tasks (section_id, description, is_checked, sort_order)
                        VALUES ($1, $2, $3, $4)
                        """,
                        [(section_id, task["description"], task.get("is_checked", True), j) for j, task in enumerate(tasks)],
                    )
