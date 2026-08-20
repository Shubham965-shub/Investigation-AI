"""
Re-rank search candidates using clean-text embeddings.

The stored `description_vector`/`root_cause_summary_vector` columns embed
each record's full raw text — batch numbers, analyst names, dates, and CAPA
boilerplate included. Comparing a clean, distilled query against that noisy
text is an apples-to-oranges comparison: confirmed empirically, a true
failure-mode match can rank 75th+ out of ~270 candidates by that comparison
alone. Re-embedding the same clean snippet the relevance filter already
extracts (description head + the root-cause statement itself, not the
narrative around it) and comparing query-to-snippet instead closes that gap —
validated to pull true matches from ranks 74-86 up to ranks 1-17 on the same
query and candidate pool.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from src.llm.client import LLMClient
from src.config.settings import settings
from src.agents.search_agent.api.services.relevance_filter import _extract_root_cause_snippet

logger = logging.getLogger(__name__)

_DESCRIPTION_CHARS = 250


def _build_rerank_snippet(candidate: dict[str, Any]) -> str:
    desc_col = settings.COLUMN_DESCRIPTION
    root_col = settings.COLUMN_ROOT_CAUSE
    description = str(candidate.get(desc_col, "") or "")[:_DESCRIPTION_CHARS]
    root_cause = _extract_root_cause_snippet(str(candidate.get(root_col, "") or ""))
    return f"{description}\n{root_cause}"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr, b_arr = np.array(a), np.array(b)
    denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if denom == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


async def rerank_by_clean_embeddings(
    llm: LLMClient,
    query: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Re-score and re-sort candidates by cosine similarity between the query
    and a clean-text embedding of each candidate, replacing `relevance_score`.

    Returns a new list sorted descending by the new score. Raises on
    embedding failure — the caller decides the fallback.
    """
    if not candidates:
        return []

    query_vec = await llm.embed_text(query)
    snippets = [_build_rerank_snippet(c) for c in candidates]
    candidate_vecs = await llm.embed_texts(snippets)

    rescored = []
    for candidate, vec in zip(candidates, candidate_vecs):
        updated = dict(candidate)
        updated["relevance_score"] = _cosine_similarity(query_vec, vec)
        rescored.append(updated)

    rescored.sort(key=lambda r: r["relevance_score"], reverse=True)
    return rescored
