"""Queries against investigation_rc_capa_sit_reviews (schema.sql) — append-only
snapshots of the report approved via "Accept and Push for SIT Lead Review". See
schema.sql's table comment for the full rationale (no real external SIT
review integration yet)."""
from __future__ import annotations

from typing import Optional

import asyncpg

from backend.clients.db_client import get_pool


async def insert_sit_review(deviation_id: int, docx: bytes, approved_by: Optional[int]) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO investigation_rc_capa_sit_reviews (deviation_id, docx, approved_by)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            deviation_id,
            docx,
            approved_by,
        )


async def fetch_latest_sit_review_status(deviation_id: int) -> Optional[str]:
    """Degrades to None (not yet pushed) if this table hasn't been run
    against the live DB yet — same convention as generated_content.sql's
    read paths, since this table shares that "not yet approved to run"
    status (see schema.sql's comment on it)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            return await conn.fetchval(
                """
                SELECT status FROM investigation_rc_capa_sit_reviews
                WHERE deviation_id = $1 ORDER BY created_at DESC LIMIT 1
                """,
                deviation_id,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return None