"""Queries against generated_content.sql's tables.

Read functions have existed since the GET endpoints were wired up. The write
functions below (save_*/replace_*) are new — called from the POST
generate/collect endpoints after a successful DS response — but are pure
application code with no bearing on the real DB until generated_content.sql
is actually run there (confirmed still not run as of 2026-07-24 — the tables
don't exist on the live DB).

The read functions below catch UndefinedTableError specifically (not a bare
except) and degrade to the same "nothing generated yet" default the caller
would see if the table existed but had no matching row — this table not
existing yet is an expected, common state pre-approval, not an anomaly, so it
is not logged as a warning. Any other DB error still propagates so a genuine
problem isn't silently swallowed.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

import asyncpg

from backend.clients.db_client import get_pool


def _parse_date(value: Any) -> Optional[datetime.date]:
    """investigation_rci_sections.due_date is a real `date` column — asyncpg
    requires an actual datetime.date object for it, not the "YYYY-MM-DD"
    string the frontend's <input type="date"> (and JSON generally) sends;
    passing the raw string through fails with "'str' object has no
    attribute 'toordinal'" (confirmed live, 2026-07-31)."""
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


async def save_problem_statement(deviation_id: int, problem_statement: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO investigation_problem_statements (deviation_id, problem_statement, generated_at)
            VALUES ($1, $2, now())
            ON CONFLICT (deviation_id) DO UPDATE
                SET problem_statement = EXCLUDED.problem_statement, generated_at = now()
            """,
            deviation_id,
            problem_statement,
        )


async def replace_evidence_items(deviation_id: int, items: List[Dict[str, Any]]) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # See replace_rci_sections' comment — same DELETE-then-INSERT
            # race applies here (called on every checkbox toggle/add), so
            # the same per-investigation advisory lock is needed.
            await conn.execute("SELECT pg_advisory_xact_lock($1)", deviation_id)
            await conn.execute("DELETE FROM investigation_evidence_items WHERE deviation_id = $1", deviation_id)
            if items:
                await conn.executemany(
                    """
                    INSERT INTO investigation_evidence_items (deviation_id, description, is_checked, sort_order)
                    VALUES ($1, $2, $3, $4)
                    """,
                    [
                        (deviation_id, item["description"], item.get("is_checked", True), i)
                        for i, item in enumerate(items)
                    ],
                )


async def replace_questionnaire_items(deviation_id: int, items: List[Dict[str, Any]]) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # See replace_rci_sections' comment — same DELETE-then-INSERT
            # race applies here (called on every checkbox toggle/add), so
            # the same per-investigation advisory lock is needed.
            await conn.execute("SELECT pg_advisory_xact_lock($1)", deviation_id)
            await conn.execute("DELETE FROM investigation_questionnaire_items WHERE deviation_id = $1", deviation_id)
            if items:
                await conn.executemany(
                    """
                    INSERT INTO investigation_questionnaire_items (deviation_id, description, is_checked, sort_order)
                    VALUES ($1, $2, $3, $4)
                    """,
                    [
                        (deviation_id, item["description"], item.get("is_checked", True), i)
                        for i, item in enumerate(items)
                    ],
                )


async def replace_rci_sections(deviation_id: int, sections: List[Dict[str, Any]]) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Serializes concurrent replace calls for the same investigation
            # (e.g. a double-clicked "Generate" plus a burst of assignee-edit
            # PUT calls firing close together) — without this, two
            # overlapping DELETE-then-INSERT sequences can each see "nothing
            # to delete yet" (the other call hasn't committed its INSERT
            # yet) and both insert their own full section set, silently
            # multiplying every section instead of one cleanly replacing the
            # other. Confirmed live: deviation_id 504419 ended up with 6
            # sections x 8 duplicate copies each, with different assignee
            # values frozen from different in-flight PUT calls. Transaction-
            # scoped — auto-released on commit/rollback, so callers just
            # block-and-wait rather than needing to release it explicitly.
            await conn.execute("SELECT pg_advisory_xact_lock($1)", deviation_id)
            # ON DELETE CASCADE on investigation_rci_tasks.section_id takes care of tasks.
            await conn.execute("DELETE FROM investigation_rci_sections WHERE deviation_id = $1", deviation_id)
            for i, section in enumerate(sections):
                section_id = await conn.fetchval(
                    """
                    INSERT INTO investigation_rci_sections
                        (deviation_id, title, correlation, due_date, assignee, sort_order, is_checked)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                    """,
                    deviation_id,
                    section["title"],
                    section.get("correlation"),
                    _parse_date(section.get("due_date")),
                    section.get("assignee"),
                    section.get("six_m_bucket"),
                    i,
                    section.get("is_checked", True),
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
