"""Conditional routing logic for the search graph."""

from __future__ import annotations

from src.agents.search_agent.graph.state import SearchState


def route_by_search_type(state: SearchState) -> str:
    """
    Decide which search path to take after query analysis.

    Returns one of three edge keys:
    - ``"keyword_only"``  → skip vector search
    - ``"semantic_only"`` → skip keyword search
    - ``"hybrid"``        → run both searches
    """
    search_type = (state.get("determined_search_type") or "").strip().lower()

    if search_type == "keyword":
        return "keyword_only"
    elif search_type == "semantic":
        return "semantic_only"
    else:
        return "hybrid"