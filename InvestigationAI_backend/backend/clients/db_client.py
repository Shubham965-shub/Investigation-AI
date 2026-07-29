"""Shared asyncpg pool for the STAR schema / auth tables Postgres instance.

Mirrors backend.clients.ds_client's create/close/get singleton pattern. If the
pool can't be created at startup (DB unreachable), we log and leave it unset
rather than crashing the app — DS-only endpoints (generate/collect/upload)
must keep working even when the DB is down.
"""
from __future__ import annotations

import logging
from typing import Optional

import asyncpg
from fastapi import HTTPException, status

from backend.config.settings import settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def create_pool() -> None:
    global _pool
    try:
        _pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=settings.DB_POOL_MIN_SIZE,
            max_size=settings.DB_POOL_MAX_SIZE,
        )
    except Exception:
        logger.warning("Could not create DB pool — DB-backed endpoints will 503 until it's reachable", exc_info=True)
        _pool = None


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not available",
        )
    return _pool
