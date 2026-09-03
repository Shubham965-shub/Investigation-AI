"""LangGraph state definition for the agentic search workflow."""

from __future__ import annotations

from typing import Any, TypedDict


class SearchState(TypedDict, total=False):
    """
    Typed dictionary carried through every node of the search graph.

    Fields marked with ``total=False`` are optional — they get populated
    progressively as the graph executes.
    """

    # ── Inputs (set once at invocation) ─────────────────────
    query: str
    search_fields: list[str]  # ["description"] | ["root_cause_summary"] | both
    search_type: str          # "keyword" | "semantic" | "auto"
    filters: dict[str, Any]   # Serialized SearchFilters

    # ── Query analysis (set by analyze_query) ───────────────
#    query_analysis: dict[str, Any]
    determined_search_type: str   # "keyword" | "semantic" | "hybrid"
    distilled_query: str          # LLM-distilled retrieval phrase, set only
                                   # when the raw query is long free text —
                                   # absent/unset otherwise (nodes fall back
                                   # to raw `query` in that case)
    distilled_query_variants: list[str]  # 2026-09-03: distillation isn't
                                   # fully deterministic even at temperature=0
                                   # (confirmed: identical input produced 3
                                   # differently-worded outputs across 5
                                   # calls) — semantic_search_node embeds and
                                   # searches EVERY variant and unions the
                                   # results, rather than gambling on one
                                   # phrasing's exact wording. distilled_query
                                   # stays the single primary variant, used
                                   # unchanged by keyword_search_node/
                                   # rerank_candidates_node.

    # ── Intermediate results ────────────────────────────────
    keyword_results: list[dict[str, Any]]
    semantic_results: list[dict[str, Any]]
    final_results: list[dict[str, Any]]

    # ── Final outputs ───────────────────────────────────────
    ranked_results: list[dict[str, Any]]
    synthesized_answer: str
    source_citations: list[dict[str, Any]]

    # ── Metadata ────────────────────────────────────────────
    error: dict[str, str] | None
