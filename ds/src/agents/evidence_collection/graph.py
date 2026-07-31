"""
LangGraph graph for the evidence collection workflow.

High-confidence path  (≥ 0.7): fetch_evidence → rephrase_evidence → format_result
Low-confidence path   (< 0.7): build_search_query → fetch_historical_data
                                → infer_evidence_from_historical_data → format_result
"""

from langgraph.graph import StateGraph, START, END

from src.agents.shared.nodes import (
    parse_input,
    fetch_archetypes,
    map_to_archetype,
    build_search_query,
    fetch_historical_data,
)
from src.agents.evidence_collection.state import EvidenceCollectionState
from src.agents.evidence_collection.nodes import (
    fetch_evidence,
    rephrase_evidence,
    infer_evidence_from_historical_data,
    format_result,
)


def _route_after_archetype_mapping(state: EvidenceCollectionState) -> str:
    return "fetch_evidence" if state.confidence_score >= 0.8 else "build_search_query"


workflow = StateGraph(EvidenceCollectionState)

workflow.add_node("parse_input", parse_input)
workflow.add_node("fetch_archetypes", fetch_archetypes)
workflow.add_node("map_to_archetype", map_to_archetype)
workflow.add_node("fetch_evidence", fetch_evidence)
workflow.add_node("rephrase_evidence", rephrase_evidence)
workflow.add_node("build_search_query", build_search_query)
workflow.add_node("fetch_historical_data", fetch_historical_data)
workflow.add_node("infer_evidence_from_historical_data", infer_evidence_from_historical_data)
workflow.add_node("format_result", format_result)

workflow.add_edge(START, "parse_input")
workflow.add_edge("parse_input", "fetch_archetypes")
workflow.add_edge("fetch_archetypes", "map_to_archetype")

workflow.add_conditional_edges(
    "map_to_archetype",
    _route_after_archetype_mapping,
    {"fetch_evidence": "fetch_evidence", "build_search_query": "build_search_query"},
)

# High-confidence path
workflow.add_edge("fetch_evidence", "rephrase_evidence")
workflow.add_edge("rephrase_evidence", "format_result")

# Low-confidence (historical) path
workflow.add_edge("build_search_query", "fetch_historical_data")
workflow.add_edge("fetch_historical_data", "infer_evidence_from_historical_data")
workflow.add_edge("infer_evidence_from_historical_data", "format_result")

workflow.add_edge("format_result", END)

evidence_collection_graph = workflow.compile()

__all__ = ["evidence_collection_graph", "EvidenceCollectionState"]