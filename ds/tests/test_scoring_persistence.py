"""Tests for persist_score's best-effort branching — no live DB required.
A fake asyncpg-shaped pool (async context managers via AsyncMock) exercises
the success and failure paths without touching Postgres."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.scoring.api.schemas import ScoringReportResponse
from src.agents.scoring.services.persistence import persist_score


def _minimal_response(**overrides) -> ScoringReportResponse:
    defaults = dict(
        score=80,
        info=[],
        event_type="OOS",
        detected_sections=["task_report"],
        overall_percentage=80.0,
        overall_marks=32.0,
        overall_max=40.0,
        task_report_execution=None,
        iq_score=None,
        iq_score_percentage=None,
        sections={},
    )
    defaults.update(overrides)
    return ScoringReportResponse(**defaults)


@pytest.mark.asyncio
async def test_no_pool_returns_none_without_touching_anything():
    result = await persist_score(None, "report.docx", _minimal_response())
    assert result is None


def _fake_pool():
    """A minimal asyncpg.Pool stand-in: pool.acquire() -> async context manager
    yielding a connection whose .transaction() is itself an async context manager."""
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.executemany = AsyncMock()

    txn_cm = MagicMock()
    txn_cm.__aenter__ = AsyncMock(return_value=None)
    txn_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=txn_cm)

    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool, conn


@pytest.mark.asyncio
async def test_successful_persist_returns_a_run_id_and_writes_run_and_checkpoints():
    pool, conn = _fake_pool()
    response = _minimal_response()
    run_id = await persist_score(pool, "report.docx", response)
    assert run_id is not None
    assert conn.execute.await_count >= 2  # DDL + insert run


@pytest.mark.asyncio
async def test_db_failure_is_swallowed_and_returns_none():
    pool, conn = _fake_pool()
    conn.execute.side_effect = RuntimeError("connection lost")
    result = await persist_score(pool, "report.docx", _minimal_response())
    assert result is None
