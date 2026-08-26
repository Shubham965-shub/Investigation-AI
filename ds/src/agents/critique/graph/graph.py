from langgraph.graph import END, START, StateGraph

from src.agents.critique.graph.nodes import (
    analyze_images,
    critique_tasks,
    extract_tasks,
    fetch_previous_recommendations,
    format_result,
    parse_document,
    validate_relevance,
)
from src.agents.critique.graph.state import TaskReportCritiqueState

_workflow = StateGraph(TaskReportCritiqueState)

_workflow.add_node("parse_document", parse_document)
_workflow.add_node("validate_relevance", validate_relevance)
_workflow.add_node("extract_tasks", extract_tasks)
_workflow.add_node("fetch_previous_recommendations", fetch_previous_recommendations)
_workflow.add_node("analyze_images", analyze_images)
_workflow.add_node("critique_tasks", critique_tasks)
_workflow.add_node("format_result", format_result)

_workflow.add_edge(START, "parse_document")

# validate_relevance, extract_tasks, and fetch_previous_recommendations only depend on
# parse_document's output (raw text / deviation_id+task_index), not on each other — run them
# concurrently instead of chaining them, so validate_relevance's and the DB lookup's latency is
# hidden behind extract_tasks' (much longer) LLM call rather than added on top of it.
_workflow.add_edge("parse_document", "validate_relevance")
_workflow.add_edge("parse_document", "extract_tasks")
_workflow.add_edge("parse_document", "fetch_previous_recommendations")

# analyze_images needs extract_tasks' problem_statement/objective for prompt context, so it
# still has to wait on that one edge.
_workflow.add_edge("extract_tasks", "analyze_images")

# critique_tasks needs extracted_tasks, image_analyses, and previous_recommendations, and must
# also wait for validate_relevance to raise before it runs — LangGraph holds it until all three
# incoming branches complete.
_workflow.add_edge("validate_relevance", "critique_tasks")
_workflow.add_edge("analyze_images", "critique_tasks")
_workflow.add_edge("fetch_previous_recommendations", "critique_tasks")

_workflow.add_edge("critique_tasks", "format_result")
_workflow.add_edge("format_result", END)

task_report_critique_graph = _workflow.compile()
