"""
Database connection pool setup and configuration with pgvector support.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Add project root to path for local module resolution
ROOT_PROJECT_PATH = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_PROJECT_PATH))

import asyncpg
from pgvector.asyncpg import register_vector
from config.settings import settings


async def create_pool() -> asyncpg.Pool:
    """Instantiate and return a configured asyncpg pool."""
    db_pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=settings.DB_POOL_MIN_SIZE,
        max_size=settings.DB_POOL_MAX_SIZE,
        init=_init_connection,
    )
    return db_pool


async def _init_connection(connection: asyncpg.Connection) -> None:
    """Setup pgvector types on each new connection spawned by the pool."""
    await register_vector(connection)


async def close_pool(pool: asyncpg.Pool) -> None:
    """Safely terminate the database connection pool."""
    await pool.close()
