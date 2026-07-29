from typing import Dict, List
from src.agents.critique.api.schemas import QuestionnaireResponse
from src.agents.problem_statement_evaluation.eval_graph.state import ActionsState
from src.agents.problem_statement_evaluation.eval_graph.builder import build_immediate_actions_graph
from src.llm.client import LLMClient
import logging
from config.settings import settings

logger = logging.getLogger(__name__)

llm = LLMClient()

def _load_prompt(filename: str) -> str:
    """Load a prompt template from the centralized prompts directory."""
    if filename == "guardrail.txt":
        prompt_path = settings.PROMPTS_DIR / filename
        return prompt_path.read_text(encoding="utf-8")
    prompt_path = settings.PROMPTS_DIR / "critique" / filename
    return prompt_path.read_text(encoding="utf-8")

guard_rail_text = _load_prompt("guardrail.txt")

async def gen_questions(event_type: str, problem_statement: str, preliminary_findings: str):
    try:
        prompt = _load_prompt("questionnaire.txt")
        questionnaire_prompt = prompt.format(event_type = event_type, problem_statement = problem_statement, preliminary_findings = preliminary_findings)
        response = await llm.get_structured_response(system_prompt=guard_rail_text, user_prompt=questionnaire_prompt, structure=QuestionnaireResponse)
        return response
    except Exception as e:
        logger.exception(f"failed generating questionnaire in service layer")
        raise 