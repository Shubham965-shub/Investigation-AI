"""Queries against investigation_rc_capa_sit_reviews (schema.sql) — append-only
snapshots of the report approved via "Accept and Push for SIT Lead Review". See
schema.sql's table comment for the full rationale (no real external SIT
review integration yet)."""
from __future__ import annotations

from typing import Optional

import asyncpg

from backend.clients.db_client import get_pool


async def insert_sit_review(deviation_id: int, docx: bytes, approved_by: Optional[int], rci_id: Optional[str] = None) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO investigation_rc_capa_sit_reviews (deviation_id, rci_id, docx, approved_by)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            deviation_id,
            rci_id,
            docx,
            approved_by,
        )


async def fetch_latest_sit_review_status(deviation_id: int, rci_id: Optional[str] = None) -> Optional[str]:
    """Degrades to None (not yet pushed) if this table doesn't exist yet —
    same convention as generated_content.sql's read paths."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            return await conn.fetchval(
                """
                SELECT status FROM investigation_rc_capa_sit_reviews
                WHERE deviation_id = $1 AND rci_id IS NOT DISTINCT FROM $2 ORDER BY created_at DESC LIMIT 1
                """,
                deviation_id,
                rci_id,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return None