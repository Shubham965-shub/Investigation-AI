"""Unit tests for LLMClient.embed_texts (batched embedding)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.llm.client import LLMClient


def _fake_embeddings_response(vectors):
    return SimpleNamespace(data=[SimpleNamespace(embedding=v) for v in vectors])


@pytest.mark.asyncio
async def test_empty_input_returns_empty_list_without_api_call():
    client = LLMClient()
    client._client.embeddings.create = AsyncMock()
    result = await client.embed_texts([])
    assert result == []
    client._client.embeddings.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_single_chunk_preserves_order():
    client = LLMClient()
    vectors = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
    client._client.embeddings.create = AsyncMock(return_value=_fake_embeddings_response(vectors))

    result = await client.embed_texts(["a", "b", "c"])

    assert result == vectors
    client._client.embeddings.create.assert_awaited_once()
    _, kwargs = client._client.embeddings.create.await_args
    assert kwargs["input"] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_chunks_requests_at_chunk_size():
    client = LLMClient()
    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        return _fake_embeddings_response([[float(call_count)]] * len(kwargs["input"]))

    client._client.embeddings.create = AsyncMock(side_effect=fake_create)

    texts = [f"text{i}" for i in range(5)]
    result = await client.embed_texts(texts, chunk_size=2)

    assert call_count == 3  # ceil(5/2)
    assert len(result) == 5
