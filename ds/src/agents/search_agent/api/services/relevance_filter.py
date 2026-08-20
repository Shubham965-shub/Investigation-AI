"""
LLM-based relevance filter.

Judges each search candidate against the current problem statement's likely
failure mechanism and drops candidates that are only topically/lexically
similar but mechanistically unrelated — cosine similarity alone can't make
that distinction since it measures textual closeness, not cause identity.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.llm.client import LLMClient
from src.config.settings import settings
from src.agents.search_agent.api.schemas import RelevanceFilterResponse

logger = logging.getLogger(__name__)

_ROOT_CAUSE_MARKER_RE = re.compile(r"(root cause|probable cause)", re.IGNORECASE)
_ROOT_CAUSE_WINDOW = 450
_DESCRIPTION_CHARS = 250


def _extract_root_cause_snippet(text: str, window: int = _ROOT_CAUSE_WINDOW) -> str:
    """Return a window of text starting at the first root/probable-cause marker.

    ``root_cause_summary`` values are full RCI narratives, not summaries — many
    front-load "Problem statement"/"Immediate containment action" boilerplate
    for 200+ characters before ever stating the cause. A plain ``text[:N]``
    head-slice would frequently hand the judge that boilerplate instead of the
    actual causal statement. Falls back to a head-slice when no marker is found.
    """
    if not text:
        return ""
    match = _ROOT_CAUSE_MARKER_RE.search(text)
    start = match.start() if match else 0
    return text[start : start + window]


def _build_candidate_payload(candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    id_col = settings.COLUMN_ID
    desc_col = settings.COLUMN_DESCRIPTION
    root_col = settings.COLUMN_ROOT_CAUSE

    payload = []
    for r in candidates:
        payload.append(
            {
                "id": str(r.get(id_col) or r.get("id") or ""),
                "description": str(r.get(desc_col, "") or "")[:_DESCRIPTION_CHARS],
                "root_cause": _extract_root_cause_snippet(str(r.get(root_col, "") or "")),
            }
        )
    return payload


async def filter_relevant(
    llm: LLMClient,
    prompt_template: str,
    guard_rail_text: str,
    query: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Judge each candidate for genuine relevance to ``query``.

    Returns only the candidates judged relevant, preserving their original
    dicts. Raises on LLM/parsing failure — the caller decides the fallback.
    """
    if not candidates:
        return []

    payload = _build_candidate_payload(candidates)
    prompt = prompt_template.format(query=query, candidates_json=json.dumps(payload))

    # Pin temperature=0 — this is a categorical judgment task (relevant vs
    # not), where run-to-run inconsistency means the same candidate can flip
    # verdicts between identical searches. get_structured_response leaves
    # temperature unset by default (falls through to the API's own default,
    # not 0), unlike LLMClient.chat() which always applies the configured
    # temperature — confirmed via direct testing that this was letting
    # judgments vary between repeated runs on the same candidate set.
    response: RelevanceFilterResponse = await llm.get_structured_response(
        system_prompt=guard_rail_text,
        user_prompt=prompt,
        structure=RelevanceFilterResponse,
        temperature=0.0,
    )

    relevant_ids = {j.id for j in response.judgments if j.relevant}

    id_col = settings.COLUMN_ID
    kept = [
        r for r in candidates
        if str(r.get(id_col) or r.get("id") or "") in relevant_ids
    ]
    logger.info(f"relevance filter: kept {len(kept)}/{len(candidates)} candidates")
    return kept
