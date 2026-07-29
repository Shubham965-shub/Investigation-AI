from src.agents.problem_statement_evaluation.eval_graph.builder import build_ps_graph
import logging
from src.agents.problem_statement_evaluation.api.schemas import ChecklistItem, CheckList, ImprovementSuggestionList, ImprovementSuggestion
from fastapi import HTTPException
from src.agents.problem_statement_evaluation.eval_graph.state import PseState
logger = logging.getLogger(__name__)
graph = build_ps_graph()

async def evaluate_ps(query: str, event_type: str):
    initial_state: PseState = {
        "query": query,
        "event_type": event_type
    }
    response = await graph.ainvoke(initial_state)
    suggestions = response["suggestions"]
    checklist = response["checklist"]

    return {
        "suggestions": suggestions,
        "checklist": checklist
    }
        # logger.exception("Graph execution failed")
        # raise HTTPException(status_code=500, detail=str(exc))
