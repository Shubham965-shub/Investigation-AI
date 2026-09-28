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
    rci_id: Optional[str] = None,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO investigation_rci_plan_exports (deviation_id, rci_id, docx, truncated_sections, approved_by)
            VALUES ($1, $2, $3, $4, $5)
            """,
            deviation_id,
            rci_id,
            docx,
            truncated_sections,
            approved_by,
        )


async def fetch_latest_rci_plan_export_docx(deviation_id: int, rci_id: Optional[str] = None) -> Optional[bytes]:
    """Used by Task Critique to read the document module 4 generated; most
    recent row wins if RCI Plan was re-exported after an edit."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            SELECT docx FROM investigation_rci_plan_exports
            WHERE deviation_id = $1 AND rci_id IS NOT DISTINCT FROM $2 ORDER BY created_at DESC LIMIT 1
            """,
            deviation_id,
            rci_id,
        )