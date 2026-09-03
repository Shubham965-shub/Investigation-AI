from typing import Dict, List
from src.agents.critique.api.schemas import QuestionnaireResponse
from src.agents.problem_statement_evaluation.eval_graph.state import ActionsState
from src.agents.problem_statement_evaluation.eval_graph.builder import build_immediate_actions_graph
from src.llm.client import LLMClient
from src.utils.deps import get_prompt_registry
import logging

logger = logging.getLogger(__name__)

llm = LLMClient()

async def gen_questions(event_type: str, problem_statement: str, preliminary_findings: str):
    try:
        registry = get_prompt_registry()
        prompt = registry.get("critique/questionnaire")
        questionnaire_prompt = prompt.format(event_type = event_type, problem_statement = problem_statement, preliminary_findings = preliminary_findings)
        response = await llm.get_structured_response(system_prompt=registry.get("guardrail"), user_prompt=questionnaire_prompt, structure=QuestionnaireResponse)
        return response
    except Exception as e:
        logger.exception(f"failed generating questionnaire in service layer")
        raise