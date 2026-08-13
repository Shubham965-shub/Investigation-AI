from langgraph.graph import END, START, StateGraph

from src.agents.critique.graph.nodes import (
    analyze_images,
    critique_tasks,
    extract_tasks,
    format_result,
    parse_document,
    validate_relevance,
)
from src.agents.critique.graph.state import TaskReportCritiqueState

_workflow = StateGraph(TaskReportCritiqueState)

_workflow.add_node("parse_document", parse_document)
_workflow.add_node("validate_relevance", validate_relevance)
_workflow.add_node("extract_tasks", extract_tasks)
_workflow.add_node("analyze_images", analyze_images)
_workflow.add_node("critique_tasks", critique_tasks)
_workflow.add_node("format_result", format_result)

_workflow.add_edge(START, "parse_document")
_workflow.add_edge("parse_document", "validate_relevance")
_workflow.add_edge("validate_relevance", "extract_tasks")
_workflow.add_edge("extract_tasks", "analyze_images")
_workflow.add_edge("analyze_images", "critique_tasks")
_workflow.add_edge("critique_tasks", "format_result")
_workflow.add_edge("format_result", END)

task_report_critique_graph = _workflow.compile()
