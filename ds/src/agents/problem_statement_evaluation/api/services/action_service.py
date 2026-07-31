# agents/problem_statement_evaluation/api/services/action_service.py
from typing import Dict, List
from ..schemas import  ImmediateActionsResponse
from src.agents.problem_statement_evaluation.eval_graph.state import ActionsState
from src.agents.problem_statement_evaluation.eval_graph.builder import build_immediate_actions_graph

import logging
logger = logging.getLogger(__name__)
graph = build_immediate_actions_graph()


async def immediate_actions(query: str, event_type: str) -> ImmediateActionsResponse:
    initial_state: ActionsState = {
        "query": query,
        "event_type": event_type
    }
    response = await graph.ainvoke(initial_state)
    return response