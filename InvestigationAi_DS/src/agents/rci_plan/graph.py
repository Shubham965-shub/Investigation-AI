"""
LangGraph graph for the RCI plan workflow.
High-confidence path (>= 0.7): fetch_rci_plan -> rephrase_rci_plan -> format_result
"""

from langgraph.graph import StateGraph, START, END

from src.agents.shared.nodes import (
    parse_input,
    fetch_archetypes,
    map_to_archetype,
)
from src.agents.rci_plan.state import RciPlanState
from src.agents.rci_plan.nodes import (
    fetch_rci_plan,
    rephrase_rci_plan,
    format_result,
)


def _route_after_archetype_mapping(state: RciPlanState) -> str:
    # High confidence path only (we do not use the historical path for RCI plan as per user request)
    return "fetch_rci_plan"


workflow = StateGraph(RciPlanState)

workflow.add_node("parse_input", parse_input)
workflow.add_node("fetch_archetypes", fetch_archetypes)
workflow.add_node("map_to_archetype", map_to_archetype)
workflow.add_node("fetch_rci_plan", fetch_rci_plan)
workflow.add_node("rephrase_rci_plan", rephrase_rci_plan)
workflow.add_node("format_result", format_result)

workflow.add_edge(START, "parse_input")
workflow.add_edge("parse_input", "fetch_archetypes")
workflow.add_edge("fetch_archetypes", "map_to_archetype")

# Route after archetype mapping (High-confidence path)
workflow.add_conditional_edges(
    "map_to_archetype",
    _route_after_archetype_mapping,
    {"fetch_rci_plan": "fetch_rci_plan"},
)

workflow.add_edge("fetch_rci_plan", "rephrase_rci_plan")
workflow.add_edge("rephrase_rci_plan", "format_result")
workflow.add_edge("format_result", END)

rci_plan_graph = workflow.compile()

__all__ = ["rci_plan_graph", "RciPlanState"]
