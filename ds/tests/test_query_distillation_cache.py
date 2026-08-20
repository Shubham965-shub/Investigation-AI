"""Unit tests for the distilled-query cache in analyze_query.

The distillation LLM call is not perfectly deterministic even at
temperature=0 — confirmed empirically (same raw text produced 3 differently
worded distillations across 3 live calls, which embedded to different
vectors and reshuffled the candidate ranking). Since problem statements are
persisted, unchanging records, caching by raw text guarantees identical
distillation — and therefore identical downstream ranking — for every repeat
search of the same investigation.
"""

from unittest.mock import AsyncMock

import pytest

from src.agents.search_agent.graph import nodes as nodes_module
from src.agents.search_agent.graph.nodes import (
    _distilled_query_cache_get,
    _distilled_query_cache_set,
    analyze_query,
)

LONG_QUERY = " ".join(["word"] * 30)  # over _DISTILLATION_WORD_THRESHOLD


@pytest.fixture(autouse=True)
def clear_cache():
    nodes_module._DISTILLED_QUERY_CACHE.clear()
    yield
    nodes_module._DISTILLED_QUERY_CACHE.clear()


class TestCacheHelpers:
    def test_get_returns_none_for_missing_key(self):
        assert _distilled_query_cache_get("nope") is None

    def test_set_then_get_roundtrips(self):
        _distilled_query_cache_set("raw text", "distilled text")
        assert _distilled_query_cache_get("raw text") == "distilled text"

    def test_cache_is_bounded_and_evicts_oldest(self):
        nodes_module._DISTILLED_QUERY_CACHE_MAX = 3
        for i in range(4):
            _distilled_query_cache_set(f"key{i}", f"val{i}")
        assert _distilled_query_cache_get("key0") is None  # evicted
        assert _distilled_query_cache_get("key3") == "val3"
        nodes_module._DISTILLED_QUERY_CACHE_MAX = 1000


class TestAnalyzeQueryCaching:
    @pytest.mark.asyncio
    async def test_second_call_with_same_query_skips_llm(self, monkeypatch):
        monkeypatch.setattr(
            nodes_module, "get_prompt_registry",
            lambda: type("R", (), {"get": staticmethod(lambda name: "{problem_statement}")})(),
        )
        llm = AsyncMock()
        llm.chat = AsyncMock(return_value="distilled phrase one")

        state = {"query": LONG_QUERY, "search_type": "auto", "filters": {}}
        result1 = await analyze_query(state, llm=llm)
        assert result1["distilled_query"] == "distilled phrase one"
        assert llm.chat.await_count == 1

        # Second call, same raw query — must reuse the cached value, not
        # call the LLM again (even if the LLM would return something
        # different this time, simulating its real non-determinism).
        llm.chat = AsyncMock(return_value="a completely different phrasing")
        result2 = await analyze_query(state, llm=llm)
        assert result2["distilled_query"] == "distilled phrase one"
        llm.chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_different_queries_are_not_conflated(self, monkeypatch):
        monkeypatch.setattr(
            nodes_module, "get_prompt_registry",
            lambda: type("R", (), {"get": staticmethod(lambda name: "{problem_statement}")})(),
        )
        llm = AsyncMock()

        llm.chat = AsyncMock(return_value="first distillation")
        state_a = {"query": LONG_QUERY + " alpha", "search_type": "auto", "filters": {}}
        result_a = await analyze_query(state_a, llm=llm)
        assert result_a["distilled_query"] == "first distillation"

        llm.chat = AsyncMock(return_value="second distillation")
        state_b = {"query": LONG_QUERY + " beta", "search_type": "auto", "filters": {}}
        result_b = await analyze_query(state_b, llm=llm)
        assert result_b["distilled_query"] == "second distillation"
        llm.chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_short_query_is_never_cached_or_distilled(self, monkeypatch):
        monkeypatch.setattr(
            nodes_module, "get_prompt_registry",
            lambda: (_ for _ in ()).throw(AssertionError("should not be called for short queries")),
        )
        llm = AsyncMock()
        state = {"query": "short query", "search_type": "auto", "filters": {}}
        result = await analyze_query(state, llm=llm)
        assert "distilled_query" not in result
        llm.chat.assert_not_awaited()
