"""
LangGraph graph for the RCI plan workflow.

High-confidence path (>= 0.7): fetch_rci_plan -> rephrase_rci_plan -> format_result
Low-confidence path  (< 0.7): build_search_query -> fetch_historical_data
                               -> infer_rci_plan_from_historical_data -> format_result

The low-confidence path was added 2026-07-30 (per the user) after
deviation_id 504419 came back with an empty plan: the active archetype-
matching prompt (shared/map_to_archetype.yaml, v6) is a strict binary
exact-match-or-nothing design, and this graph previously had no fallback at
all when that returned "no match" — see rci_plan/nodes.py's
infer_rci_plan_from_historical_data for the drafting logic, which mirrors
evidence_collection's existing low-confidence path.
"""

from langgraph.graph import StateGraph, START, END

from src.agents.shared.nodes import (
    parse_input,
    fetch_archetypes,
    map_to_archetype,
    build_search_query,
    fetch_historical_data,
)
from src.agents.rci_plan.state import RciPlanState
from src.agents.rci_plan.nodes import (
    fetch_rci_plan,
    rephrase_rci_plan,
    infer_rci_plan_from_historical_data,
    format_result,
)


def _route_after_archetype_mapping(state: RciPlanState) -> str:
    return "fetch_rci_plan" if state.confidence_score >= 0.7 else "build_search_query"


workflow = StateGraph(RciPlanState)

workflow.add_node("parse_input", parse_input)
workflow.add_node("fetch_archetypes", fetch_archetypes)
workflow.add_node("map_to_archetype", map_to_archetype)
workflow.add_node("fetch_rci_plan", fetch_rci_plan)
workflow.add_node("rephrase_rci_plan", rephrase_rci_plan)
workflow.add_node("build_search_query", build_search_query)
workflow.add_node("fetch_historical_data", fetch_historical_data)
workflow.add_node("infer_rci_plan_from_historical_data", infer_rci_plan_from_historical_data)
workflow.add_node("format_result", format_result)

workflow.add_edge(START, "parse_input")
workflow.add_edge("parse_input", "fetch_archetypes")
workflow.add_edge("fetch_archetypes", "map_to_archetype")

# Route after archetype mapping
workflow.add_conditional_edges(
    "map_to_archetype",
    _route_after_archetype_mapping,
    {"fetch_rci_plan": "fetch_rci_plan", "build_search_query": "build_search_query"},
)

# High-confidence path
workflow.add_edge("fetch_rci_plan", "rephrase_rci_plan")
workflow.add_edge("rephrase_rci_plan", "format_result")

# Low-confidence (historical) path
workflow.add_edge("build_search_query", "fetch_historical_data")
workflow.add_edge("fetch_historical_data", "infer_rci_plan_from_historical_data")
workflow.add_edge("infer_rci_plan_from_historical_data", "format_result")

workflow.add_edge("format_result", END)

rci_plan_graph = workflow.compile()

__all__ = ["rci_plan_graph", "RciPlanState"]
