"""Unit tests for the clean-embedding candidate reranker."""

from unittest.mock import AsyncMock

import pytest

from src.agents.search_agent.api.services.rerank import (
    _build_rerank_snippet,
    _cosine_similarity,
    rerank_by_clean_embeddings,
)


class TestBuildRerankSnippet:
    def test_combines_description_and_root_cause_snippet(self):
        candidate = {
            "description": "x" * 500,
            "root_cause_summary": "Problem statement: filler text. Root Cause: heater failed.",
        }
        snippet = _build_rerank_snippet(candidate)
        assert len(snippet.split("\n")[0]) == 250
        assert "Root Cause:" in snippet

    def test_handles_missing_fields(self):
        assert _build_rerank_snippet({}) == "\n"


class TestCosineSimilarity:
    def test_identical_vectors_score_one(self):
        assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector_returns_zero_not_nan(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


class TestRerankByCleanEmbeddings:
    @pytest.mark.asyncio
    async def test_empty_candidates_skips_embedding_calls(self):
        llm = AsyncMock()
        result = await rerank_by_clean_embeddings(llm=llm, query="q", candidates=[])
        assert result == []
        llm.embed_text.assert_not_called()
        llm.embed_texts.assert_not_called()

    @pytest.mark.asyncio
    async def test_resorts_by_new_cosine_score_and_preserves_fields(self):
        candidates = [
            {"deviation_id": 1, "description": "a", "relevance_score": 0.9},
            {"deviation_id": 2, "description": "b", "relevance_score": 0.1},
        ]
        llm = AsyncMock()
        llm.embed_text = AsyncMock(return_value=[1.0, 0.0])
        # candidate 1's vector is orthogonal (low new score); candidate 2's
        # vector matches the query exactly (high new score) — the opposite
        # of their original relevance_score ordering.
        llm.embed_texts = AsyncMock(return_value=[[0.0, 1.0], [1.0, 0.0]])

        result = await rerank_by_clean_embeddings(llm=llm, query="q", candidates=candidates)

        assert [r["deviation_id"] for r in result] == [2, 1]
        assert result[0]["relevance_score"] == pytest.approx(1.0)
        assert result[1]["relevance_score"] == pytest.approx(0.0)
        # original dict fields (besides relevance_score) are preserved
        assert result[0]["description"] == "b"

    @pytest.mark.asyncio
    async def test_does_not_mutate_input_candidates(self):
        candidates = [{"deviation_id": 1, "description": "a", "relevance_score": 0.9}]
        llm = AsyncMock()
        llm.embed_text = AsyncMock(return_value=[1.0, 0.0])
        llm.embed_texts = AsyncMock(return_value=[[1.0, 0.0]])

        await rerank_by_clean_embeddings(llm=llm, query="q", candidates=candidates)

        assert candidates[0]["relevance_score"] == 0.9
