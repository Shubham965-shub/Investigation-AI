"""Queries against investigation_task_critique_source_documents (schema.sql)
— a manually-uploaded stand-in RCI Plan document, used by Task Critique only
when module 4 hasn't produced a real export yet. See schema.sql's table
comment for the full rationale."""
from __future__ import annotations

from typing import Optional, Tuple

import asyncpg

from backend.clients.db_client import get_pool


async def fetch_source_document(deviation_id: int, rci_id: Optional[str] = None) -> Optional[Tuple[bytes, str]]:
    """Degrades to None if this table doesn't exist yet — same convention
    as generated_content.sql's read paths."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT docx, file_name FROM investigation_task_critique_source_documents WHERE deviation_id = $1 AND rci_id IS NOT DISTINCT FROM $2",
                deviation_id,
                rci_id,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return None
        return (row["docx"], row["file_name"]) if row else None


async def upsert_source_document(deviation_id: int, file_name: str, docx: bytes, rci_id: Optional[str] = None) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO investigation_task_critique_source_documents (deviation_id, rci_id, file_name, docx)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (deviation_id, rci_id) DO UPDATE
                SET file_name = EXCLUDED.file_name, docx = EXCLUDED.docx, uploaded_at = now()
            """,
            deviation_id,
            rci_id,
            file_name,
            docx,
        )