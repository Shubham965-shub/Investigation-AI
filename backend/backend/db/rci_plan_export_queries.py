"""Queries against investigation_rci_plan_exports (schema.sql) — append-only
snapshots of the RCI Plan .docx generated each time "Accept and Push to TW"
is approved. See schema.sql's table comment for the full rationale."""
from __future__ import annotations

from typing import Optional

from backend.clients.db_client import get_pool


async def insert_rci_plan_export(
    deviation_id: int,
    docx: bytes,
    truncated_sections: int,
    approved_by: Optional[int],
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO investigation_rci_plan_exports (deviation_id, docx, truncated_sections, approved_by)
            VALUES ($1, $2, $3, $4)
            """,
            deviation_id,
            docx,
            truncated_sections,
            approved_by,
        )