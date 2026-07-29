"""FastAPI dependency providers for DB pool, LLM client, and prompt registry."""

from __future__ import annotations

import asyncpg

from src.llm.client import LLMClient

# These are set during app startup (see app.py lifespan).
_pool: asyncpg.Pool | None = None
_llm: LLMClient | None = None
_prompt_registry = None  # PromptRegistry — avoid circular import with type hint


def set_pool(pool: asyncpg.Pool) -> None:
    global _pool
    _pool = pool


def set_llm(llm: LLMClient) -> None:
    global _llm
    _llm = llm


def set_prompt_registry(registry) -> None:
    global _prompt_registry
    _prompt_registry = registry


async def get_db_pool() -> asyncpg.Pool:
    assert _pool is not None, "DB pool not initialised"
    return _pool


async def get_llm_client() -> LLMClient:
    assert _llm is not None, "LLM client not initialised"
    return _llm


def get_prompt_registry():
    assert _prompt_registry is not None, "PromptRegistry not initialised"
    return _prompt_registry
