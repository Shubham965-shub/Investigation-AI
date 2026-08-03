"""Queries against the auth bootstrap tables (schema.sql) — athena_users/
athena_roles/athena_api_call_trails, applied to the shared DB 2026-07-31."""
from __future__ import annotations

from typing import Any, Dict, Optional

from backend.clients.db_client import get_pool


async def fetch_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.username, u.password_hash, u.is_active, u.full_name, r.name AS role
            FROM athena_users u
            LEFT JOIN athena_roles r ON r.id = u.role_id
            WHERE u.username = $1
            """,
            username,
        )
        return dict(row) if row else None


async def record_api_call(
    user_id: Optional[int],
    method: str,
    path: str,
    status_code: int,
    duration_ms: int,
    ip_address: Optional[str],
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO athena_api_call_trails (user_id, method, path, status_code, duration_ms, ip_address)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            user_id,
            method,
            path,
            status_code,
            duration_ms,
            ip_address,
        )