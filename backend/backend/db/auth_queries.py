"""Queries against the auth bootstrap tables (schema.sql) — athena_users/
athena_roles/athena_api_call_trails, applied to the shared DB 2026-07-31."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import asyncpg

from backend.clients.db_client import get_pool


async def fetch_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.username, u.password_hash, u.is_active, u.full_name, u.investigator_name, r.name AS role
            FROM athena_users u
            LEFT JOIN athena_roles r ON r.id = u.role_id
            WHERE u.username = $1
            """,
            username,
        )
        return dict(row) if row else None


async def record_login(user_id: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE athena_users SET last_login = now() WHERE id = $1", user_id)


# ── User Management (admin-only) ───────────────────────────────────────────


async def fetch_all_users() -> List[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT u.id, u.username, u.full_name, r.name AS role, u.is_active, u.created_at, u.last_login,
                   u.investigator_name
            FROM athena_users u
            LEFT JOIN athena_roles r ON r.id = u.role_id
            ORDER BY u.id
            """
        )


async def fetch_all_role_names() -> List[str]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT name FROM athena_roles ORDER BY name")
        return [r["name"] for r in rows]


async def fetch_role_id_by_name(role_name: str) -> Optional[int]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT id FROM athena_roles WHERE name = $1", role_name)


async def create_user(
    username: str, full_name: str, password_hash: str, role_id: int, investigator_name: Optional[str] = None
) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO athena_users (username, password_hash, role_id, full_name, investigator_name, is_active)
            VALUES ($1, $2, $3, $4, $5, TRUE)
            RETURNING id
            """,
            username,
            password_hash,
            role_id,
            full_name,
            investigator_name,
        )


async def update_user_role(user_id: int, role_id: int) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("UPDATE athena_users SET role_id = $1 WHERE id = $2", role_id, user_id)
        return result == "UPDATE 1"


async def update_user_investigator_name(user_id: int, investigator_name: Optional[str]) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE athena_users SET investigator_name = $1 WHERE id = $2", investigator_name or None, user_id
        )
        return result == "UPDATE 1"


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