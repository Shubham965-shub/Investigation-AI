"""LangGraph state definition for the Problem Statement Evaluation workflow."""

from __future__ import annotations

from typing import Any, TypedDict, List


class PseState(TypedDict, total=False):
    """
    Typed dictionary carried through every node of the search graph.

    Fields marked with ``total=False`` are optional — they get populated
    progressively as the graph executes.
    """

    # ── Event Type
    event_type: str

    # ── Inputs (set once at invocation) ─────────────────────
    query: str
    # ── Node Outputs
    checklist: List[Any]
    suggestions: List[Any]
    
    response: List[Any]
    # ── Metadata ────────────────────────────────────────────
    error: dict[str, str] | None

class ActionsState(TypedDict, total=False):
    """
    Typed dictionary carried through every node of the search graph.

    Fields marked with ``total=False`` are optional — they get populated
    progressively as the graph executes.
    """

    # ── Event Type
    event_type: str

    # ── Inputs (set once at invocation) ─────────────────────
    query: str
    # ── Node Outputs
    sop_actions: List[Any]
    llm_actions: List[Any]
    
    response: List[Any]
    # ── Metadata ────────────────────────────────────────────
    error: dict[str, str] | None