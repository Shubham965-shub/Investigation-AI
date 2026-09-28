"""
LangGraph graph for the interview questionnaire workflow.

High-confidence path  (>= 0.7): fetch_questions -> rephrase_questions -> format_result
Low-confidence path   (<  0.7): build_search_query -> fetch_historical_data
                                -> infer_questions_from_historical_data -> format_result
"""

from langgraph.graph import StateGraph, START, END

from src.agents.shared.nodes import (
    parse_input,
    fetch_archetypes,
    map_to_archetype,
    build_search_query,
    fetch_historical_data,
)
from src.agents.interview_questionnaire.state import InterviewQuestionCollectionState
from src.agents.interview_questionnaire.nodes import (
    fetch_questions,
    rephrase_questions,
    infer_questions_from_historical_data,
    format_result,
)


def _route_after_archetype_mapping(state: InterviewQuestionCollectionState) -> str:
    return "fetch_questions" if state.confidence_score >= 0.7 else "build_search_query"


async def _map_to_archetype_node(
    state: InterviewQuestionCollectionState,
) -> InterviewQuestionCollectionState:
    # Threads state.rci_id through explicitly — groundwork only, map_to_archetype
    # doesn't act on it yet.
    return await map_to_archetype(state, rci_id=state.rci_id)


workflow = StateGraph(InterviewQuestionCollectionState)

workflow.add_node("parse_input", parse_input)
workflow.add_node("fetch_archetypes", fetch_archetypes)
workflow.add_node("map_to_archetype", _map_to_archetype_node)
workflow.add_node("fetch_questions", fetch_questions)
workflow.add_node("rephrase_questions", rephrase_questions)
workflow.add_node("build_search_query", build_search_query)
workflow.add_node("fetch_historical_data", fetch_historical_data)
workflow.add_node("infer_questions_from_historical_data", infer_questions_from_historical_data)
workflow.add_node("format_result", format_result)

workflow.add_edge(START, "parse_input")
workflow.add_edge("parse_input", "fetch_archetypes")
workflow.add_edge("fetch_archetypes", "map_to_archetype")

workflow.add_conditional_edges(
    "map_to_archetype",
    _route_after_archetype_mapping,
    {"fetch_questions": "fetch_questions", "build_search_query": "build_search_query"},
)

# High-confidence path
workflow.add_edge("fetch_questions", "rephrase_questions")
workflow.add_edge("rephrase_questions", "format_result")

# Low-confidence (historical) path
workflow.add_edge("build_search_query", "fetch_historical_data")
workflow.add_edge("fetch_historical_data", "infer_questions_from_historical_data")
workflow.add_edge("infer_questions_from_historical_data", "format_result")

workflow.add_edge("format_result", END)

interview_questionnaire_graph = workflow.compile()

__all__ = ["interview_questionnaire_graph", "InterviewQuestionCollectionState"]
