"""Unit tests for the relevance filter service — pure-function snippet/payload
building tests plus a mocked-LLM test for the filtering logic itself."""

from unittest.mock import AsyncMock

import pytest

from src.agents.search_agent.api.services.relevance_filter import (
    _build_candidate_payload,
    _extract_root_cause_snippet,
    filter_relevant,
)
from src.agents.search_agent.api.schemas import RelevanceFilterResponse


class TestExtractRootCauseSnippet:
    def test_empty_input_returns_empty_string(self):
        assert _extract_root_cause_snippet("") == ""

    def test_falls_back_to_head_slice_when_no_marker_found(self):
        text = "x" * 1000
        assert _extract_root_cause_snippet(text, window=50) == text[:50]

    def test_starts_window_at_first_marker(self):
        preamble = "Problem statement: on 01/01/2025 analyst observed an anomaly. " * 3
        text = preamble + "Root Cause: the heater failed due to a burnt fuse."
        snippet = _extract_root_cause_snippet(text, window=100)
        assert snippet.startswith("Root Cause:")

    def test_marker_match_is_case_insensitive(self):
        text = "some preamble text here " * 5 + "PROBABLE CAUSE: valve malfunction."
        snippet = _extract_root_cause_snippet(text, window=100)
        assert snippet.startswith("PROBABLE CAUSE:")

    def test_prefers_earliest_marker_occurrence(self):
        text = "Root Cause investigation initiated. " + "filler " * 10 + "Root Cause: actual finding here."
        snippet = _extract_root_cause_snippet(text, window=500)
        assert snippet.startswith("Root Cause investigation initiated.")


class TestBuildCandidatePayload:
    def test_truncates_description_and_extracts_root_cause(self):
        candidates = [
            {
                "deviation_id": 123,
                "description": "x" * 500,
                "root_cause_summary": "Problem statement: filler. Root Cause: heater failed.",
            }
        ]
        payload = _build_candidate_payload(candidates)
        assert len(payload) == 1
        assert payload[0]["id"] == "123"
        assert len(payload[0]["description"]) == 250
        assert payload[0]["root_cause"].startswith("Root Cause:")

    def test_handles_missing_fields_gracefully(self):
        candidates = [{"deviation_id": 5}]
        payload = _build_candidate_payload(candidates)
        assert payload == [{"id": "5", "description": "", "root_cause": ""}]

    def test_empty_candidates_returns_empty_payload(self):
        assert _build_candidate_payload([]) == []


class TestFilterRelevant:
    @pytest.mark.asyncio
    async def test_empty_candidates_skips_llm_call(self):
        llm = AsyncMock()
        result = await filter_relevant(
            llm=llm, prompt_template="{query}{candidates_json}",
            guard_rail_text="guardrail", query="q", candidates=[],
        )
        assert result == []
        llm.get_structured_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_keeps_only_relevant_ids_and_preserves_original_dicts(self):
        candidates = [
            {"deviation_id": 1, "description": "a"},
            {"deviation_id": 2, "description": "b"},
            {"deviation_id": 3, "description": "c"},
        ]
        llm = AsyncMock()
        llm.get_structured_response = AsyncMock(
            return_value=RelevanceFilterResponse.model_validate(
                {
                    "judgments": [
                        {"id": "1", "relevant": True, "reason": "same mechanism"},
                        {"id": "2", "relevant": False, "reason": "different cause"},
                        {"id": "3", "relevant": True, "reason": "same mechanism"},
                    ]
                }
            )
        )

        result = await filter_relevant(
            llm=llm, prompt_template="QUERY: {query}\nCANDIDATES: {candidates_json}",
            guard_rail_text="guardrail", query="RH excursion", candidates=candidates,
        )

        assert result == [candidates[0], candidates[2]]
        # Judged _JUDGMENT_ATTEMPTS (2) times, not once — see filter_relevant's
        # own docstring: temperature=0 alone doesn't fully eliminate run-to-run
        # LLM flip-flopping, so every candidate set is judged 2x and every
        # call's "relevant" verdicts are unioned (2026-09-03, per the user;
        # scaled down from an initial 3x to control token cost).
        assert llm.get_structured_response.await_count == 2

    @pytest.mark.asyncio
    async def test_all_irrelevant_returns_empty_list(self):
        candidates = [{"deviation_id": 1, "description": "a"}]
        llm = AsyncMock()
        llm.get_structured_response = AsyncMock(
            return_value=RelevanceFilterResponse.model_validate(
                {"judgments": [{"id": "1", "relevant": False, "reason": "unrelated"}]}
            )
        )

        result = await filter_relevant(
            llm=llm, prompt_template="{query}{candidates_json}",
            guard_rail_text="guardrail", query="q", candidates=candidates,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_borderline_candidate_kept_if_relevant_in_any_single_attempt(self):
        """The actual bug this fix addresses (2026-09-03, per the user): a
        genuinely relevant candidate judged "relevant" on some attempts and
        "not relevant" on others (temperature=0 non-determinism) must still
        be kept — a single "not relevant" roll must not silently drop it."""
        candidates = [{"deviation_id": 1, "description": "a"}]
        relevant_response = RelevanceFilterResponse.model_validate(
            {"judgments": [{"id": "1", "relevant": True, "reason": "same mechanism"}]}
        )
        not_relevant_response = RelevanceFilterResponse.model_validate(
            {"judgments": [{"id": "1", "relevant": False, "reason": "different cause"}]}
        )
        llm = AsyncMock()
        # 1 of 2 attempts says "not relevant" — union still keeps it since
        # the other attempt found it relevant.
        llm.get_structured_response = AsyncMock(
            side_effect=[not_relevant_response, relevant_response]
        )

        result = await filter_relevant(
            llm=llm, prompt_template="{query}{candidates_json}",
            guard_rail_text="guardrail", query="q", candidates=candidates,
        )
        assert result == candidates

    @pytest.mark.asyncio
    async def test_failed_judgment_attempts_dont_block_the_others(self):
        """One attempt raising (rate limit, timeout, etc.) must not fail the
        whole filter — the surviving attempt's verdict still counts."""
        candidates = [{"deviation_id": 1, "description": "a"}]
        relevant_response = RelevanceFilterResponse.model_validate(
            {"judgments": [{"id": "1", "relevant": True, "reason": "same mechanism"}]}
        )
        llm = AsyncMock()
        llm.get_structured_response = AsyncMock(
            side_effect=[RuntimeError("boom"), relevant_response]
        )

        result = await filter_relevant(
            llm=llm, prompt_template="{query}{candidates_json}",
            guard_rail_text="guardrail", query="q", candidates=candidates,
        )
        assert result == candidates

    @pytest.mark.asyncio
    async def test_all_judgment_attempts_failing_raises(self):
        candidates = [{"deviation_id": 1, "description": "a"}]
        llm = AsyncMock()
        llm.get_structured_response = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError):
            await filter_relevant(
                llm=llm, prompt_template="{query}{candidates_json}",
                guard_rail_text="guardrail", query="q", candidates=candidates,
            )
