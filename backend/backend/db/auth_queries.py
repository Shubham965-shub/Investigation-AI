"""Queries against the auth bootstrap tables (schema.sql) — athena_users/
athena_roles/athena_api_call_trails, applied to the shared DB 2026-07-31."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import asyncpg

from backend.clients.db_client import get_pool


async def fetch_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Case-insensitive on purpose (2026-09-28, per the user) — matches the
    LOWER(username) unique index in schema.sql, so "Foo@x.com" and "foo@x.com"
    resolve to the same, single account rather than requiring an exact-case match."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.username, u.password_hash, u.is_active, u.full_name, u.investigator_name, r.name AS role
            FROM athena_users u
            LEFT JOIN athena_roles r ON r.id = u.role_id
            WHERE LOWER(u.username) = LOWER($1)
            """,
            username,
        )
        return dict(row) if row else None


async def record_login(user_id: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE athena_users SET last_login = now() WHERE id = $1", user_id)


async def fetch_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """For the self-service change-password flow, to re-verify the caller's current password
    server-side rather than trusting the JWT alone."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, username, password_hash, is_active FROM athena_users WHERE id = $1", user_id
        )
        return dict(row) if row else None


async def update_user_password(user_id: int, password_hash: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE athena_users SET password_hash = $1 WHERE id = $2", password_hash, user_id)


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


async def update_user_active_status(user_id: int, is_active: bool) -> bool:
    """Deactivation is this app's "remove a user" mechanism (2026-10-01, per the user) — a hard
    DELETE would violate the FK every generated_by/uploaded_by column holds against athena_users,
    and would destroy real attribution history (see this session's Manikandan K case). Deactivated
    accounts fail login (routers/auth.py's login() checks is_active) but keep all their history."""
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("UPDATE athena_users SET is_active = $1 WHERE id = $2", is_active, user_id)
        return result == "UPDATE 1"


async def update_user_investigator_name(user_id: int, investigator_name: Optional[str]) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE athena_users SET investigator_name = $1 WHERE id = $2", investigator_name or None, user_id
        )
        return result == "UPDATE 1"


async def fetch_audit_trail(record_id: str, rci_id: str) -> List[Dict[str, Any]]:
    """Admin-only audit trail for one record/RCI (2026-10-01, per the user) — every API call
    whose path contains "/<record_id>/<rci_id>" as consecutive path segments (not a naive
    substring match, which could false-positive on e.g. record_id "5039" inside "50390"). `rci_id`
    is the raw path segment as logged — including the literal "none" sentinel for a no-RCI
    record — never the DB-normalized None; every logged path spells out a real segment here.
    Role shown is the user's CURRENT role (athena_users.role_id), not necessarily the role they
    held at call time — this app doesn't version roles historically anywhere, same caveat as
    require_admin's own JWT-roles-claim check elsewhere in this file."""
    pool = get_pool()
    pattern = rf"(^|/){re.escape(record_id)}/{re.escape(rci_id)}(/|$)"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT t.created_at, t.method, t.path, t.status_code, t.duration_ms,
                   u.username, u.full_name, r.name AS role
            FROM athena_api_call_trails t
            LEFT JOIN athena_users u ON u.id = t.user_id
            LEFT JOIN athena_roles r ON r.id = u.role_id
            WHERE t.path ~ $1 AND t.method != 'OPTIONS'
            ORDER BY t.created_at DESC
            """,
            pattern,
        )
        return [dict(row) for row in rows]


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