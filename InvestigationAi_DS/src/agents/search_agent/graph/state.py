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
