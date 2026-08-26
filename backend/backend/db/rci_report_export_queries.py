"""Queries against investigation_rci_report_exports (schema.sql) — append-only
snapshots of the RCI Report .docx generated each time "Accept and Push to TW"
is approved. See schema.sql's table comment; same convention as
rci_plan_export_queries.py."""
from __future__ import annotations

from typing import Optional

from backend.clients.db_client import get_pool


async def insert_rci_report_export(deviation_id: int, docx: bytes, approved_by: Optional[int]) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO investigation_rci_report_exports (deviation_id, docx, approved_by)
            VALUES ($1, $2, $3)
            """,
            deviation_id,
            docx,
            approved_by,
        )
