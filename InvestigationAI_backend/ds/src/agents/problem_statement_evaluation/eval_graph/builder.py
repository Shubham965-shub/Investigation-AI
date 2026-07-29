from langgraph.graph import StateGraph, END
from src.agents.problem_statement_evaluation.eval_graph.nodes import (
    analyze_problem_statement,
    improvement_suggestion,
    generate_immediate_actions
)
from src.agents.problem_statement_evaluation.eval_graph.state import PseState, ActionsState
from src.llm.client import LLMClient

def build_ps_graph():
    ps_graph = StateGraph(PseState)

    ps_graph.add_node("ps_analysis", analyze_problem_statement)
    ps_graph.add_node("suggestions_node", improvement_suggestion)
    ps_graph.set_entry_point("ps_analysis")
    ps_graph.add_edge("ps_analysis", "suggestions_node")
    ps_graph.add_edge("suggestions_node", END)

    return ps_graph.compile()


def build_immediate_actions_graph():
    print("Test log")
    graph = StateGraph(ActionsState)
    graph.add_node('generate_immediate_actions', generate_immediate_actions)
    graph.set_entry_point("generate_immediate_actions")
    graph.add_edge("generate_immediate_actions", END)
    return graph.compile()