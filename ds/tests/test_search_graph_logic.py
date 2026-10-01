"""Pure-logic tests for the search_agent graph's routing and state-shaping
helpers — no DB/LLM required. route_by_search_type decides which path the
graph takes; _normalize_date/_filters_from_dict shape the raw request dict
into a SearchFilters; the distilled-query cache is a plain LRU dict;
combine_results_node is `async def` but does no I/O, only merging/sorting."""

from datetime import datetime

import pytest

from src.agents.search_agent.graph.edges import route_by_search_type
from src.agents.search_agent.graph import nodes as nodes_mod
from src.agents.search_agent.graph.nodes import (
    _distilled_query_cache_get,
    _distilled_query_cache_set,
    _filters_from_dict,
    _normalize_date,
    combine_results_node,
)


class TestRouteBySearchType:
    def test_keyword_routes_to_keyword_only(self):
        assert route_by_search_type({"determined_search_type": "keyword"}) == "keyword_only"

    def test_semantic_routes_to_semantic_only(self):
        assert route_by_search_type({"determined_search_type": "semantic"}) == "semantic_only"

    def test_anything_else_routes_to_hybrid(self):
        assert route_by_search_type({"determined_search_type": "hybrid"}) == "hybrid"
        assert route_by_search_type({"determined_search_type": "auto"}) == "hybrid"

    def test_missing_key_defaults_to_hybrid(self):
        assert route_by_search_type({}) == "hybrid"

    def test_matching_is_case_and_whitespace_insensitive(self):
        assert route_by_search_type({"determined_search_type": "  Keyword  "}) == "keyword_only"
        assert route_by_search_type({"determined_search_type": "SEMANTIC"}) == "semantic_only"


class TestNormalizeDate:
    def test_null_sentinels_return_none(self):
        assert _normalize_date("null") is None
        assert _normalize_date(None) is None
        assert _normalize_date("") is None
        assert _normalize_date("None") is None

    def test_iso_string_is_parsed(self):
        assert _normalize_date("2026-01-15") == datetime.fromisoformat("2026-01-15")

    def test_real_datetime_passes_through_unchanged(self):
        dt = datetime(2026, 1, 15)
        assert _normalize_date(dt) is dt

    def test_other_types_pass_through_unchanged(self):
        assert _normalize_date(12345) == 12345


class TestFiltersFromDict:
    def test_empty_dict_produces_all_none_filters(self):
        filters = _filters_from_dict({})
        assert filters.qe_type is None
        assert filters.date_from is None
        assert filters.locations is None
        assert filters.exclude_id is None

    def test_null_string_sentinels_are_treated_as_none(self):
        filters = _filters_from_dict(
            {"qe_type": "null", "locations": "null", "instruments": None, "exclude_id": "null"}
        )
        assert filters.qe_type is None
        assert filters.locations is None
        assert filters.instruments is None
        assert filters.exclude_id is None

    def test_real_values_pass_through(self):
        filters = _filters_from_dict(
            {
                "qe_type": "Deviation",
                "date_from": "2026-01-01",
                "date_to": "2026-02-01",
                "locations": ["Site A"],
                "exclude_id": "12345",
            }
        )
        assert filters.qe_type == "Deviation"
        assert filters.date_from == datetime.fromisoformat("2026-01-01")
        assert filters.date_to == datetime.fromisoformat("2026-02-01")
        assert filters.locations == ["Site A"]
        assert filters.exclude_id == "12345"


class TestDistilledQueryCache:
    @pytest.fixture(autouse=True)
    def _clean_cache(self):
        nodes_mod._DISTILLED_QUERY_CACHE.clear()
        yield
        nodes_mod._DISTILLED_QUERY_CACHE.clear()

    def test_miss_returns_none(self):
        assert _distilled_query_cache_get("not cached") is None

    def test_set_then_get_returns_the_stored_value(self):
        _distilled_query_cache_set("raw text", ["variant 1", "variant 2"])
        assert _distilled_query_cache_get("raw text") == ["variant 1", "variant 2"]

    def test_eviction_drops_the_least_recently_used_entry(self, monkeypatch):
        monkeypatch.setattr(nodes_mod, "_DISTILLED_QUERY_CACHE_MAX", 2)
        _distilled_query_cache_set("a", ["A"])
        _distilled_query_cache_set("b", ["B"])
        _distilled_query_cache_set("c", ["C"])  # evicts "a" (oldest, never re-touched)
        assert _distilled_query_cache_get("a") is None
        assert _distilled_query_cache_get("b") == ["B"]
        assert _distilled_query_cache_get("c") == ["C"]

    def test_get_marks_entry_as_recently_used_protecting_it_from_eviction(self, monkeypatch):
        monkeypatch.setattr(nodes_mod, "_DISTILLED_QUERY_CACHE_MAX", 2)
        _distilled_query_cache_set("a", ["A"])
        _distilled_query_cache_set("b", ["B"])
        _distilled_query_cache_get("a")  # touch "a" so "b" becomes the oldest
        _distilled_query_cache_set("c", ["C"])  # evicts "b", not "a"
        assert _distilled_query_cache_get("a") == ["A"]
        assert _distilled_query_cache_get("b") is None


class TestCombineResultsNode:
    @pytest.mark.asyncio
    async def test_merges_keyword_and_semantic_results(self):
        state = {
            "keyword_results": [{"id": 1, "relevance_score": 0.5}],
            "semantic_results": [{"id": 2, "relevance_score": 0.9}],
            "determined_search_type": "hybrid",
        }
        result = await combine_results_node(state)
        ids = {r["id"] for r in result["final_results"]}
        assert ids == {1, 2}

    @pytest.mark.asyncio
    async def test_dedups_by_id_keeping_the_higher_score(self):
        state = {
            "keyword_results": [{"id": 1, "relevance_score": 0.3}],
            "semantic_results": [{"id": 1, "relevance_score": 0.8}],
            "determined_search_type": "hybrid",
        }
        result = await combine_results_node(state)
        assert len(result["final_results"]) == 1
        assert result["final_results"][0]["relevance_score"] == 0.8

    @pytest.mark.asyncio
    async def test_results_missing_an_id_are_dropped(self):
        state = {
            "keyword_results": [{"relevance_score": 0.3}],
            "semantic_results": [],
            "determined_search_type": "hybrid",
        }
        result = await combine_results_node(state)
        assert result["final_results"] == []

    @pytest.mark.asyncio
    async def test_hybrid_results_are_sorted_by_relevance_score_descending(self):
        state = {
            "keyword_results": [{"id": 1, "relevance_score": 0.2}, {"id": 2, "relevance_score": 0.9}],
            "semantic_results": [],
            "determined_search_type": "hybrid",
        }
        result = await combine_results_node(state)
        assert [r["id"] for r in result["final_results"]] == [2, 1]

    @pytest.mark.asyncio
    async def test_pure_keyword_results_are_not_resorted(self):
        state = {
            "keyword_results": [{"id": 1, "relevance_score": 0.2}, {"id": 2, "relevance_score": 0.9}],
            "semantic_results": [],
            "determined_search_type": "keyword",
        }
        result = await combine_results_node(state)
        # Original (date-sorted upstream) order preserved for pure keyword mode.
        assert [r["id"] for r in result["final_results"]] == [1, 2]
