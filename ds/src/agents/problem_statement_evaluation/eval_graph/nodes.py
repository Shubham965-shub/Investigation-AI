"""
Docstring for agents.problem_statement_evaluation.graph.nodes
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import asyncpg

from src.llm.client import LLMClient
from src.utils.deps import get_prompt_registry
from src.agents.problem_statement_evaluation.api.schemas import CheckList, ImprovementSuggestionList, LLMActions
from src.agents.problem_statement_evaluation.eval_graph.state import PseState, ActionsState
from src.agents.problem_statement_evaluation.domain.sops import SOP_BY_EVENT_TYPE
logger = logging.getLogger(__name__)

llm = LLMClient()


async def analyze_problem_statement(
        state: PseState
):
    """
    Docstring for analyze_problem_statement
    
    :param state: Description
    :type state: PseState
    :param llm: Description
    :type llm: LLMClient
    """
    try:
        event_type = state.get("event_type", "")
        query = state.get("query", "")
    except Exception as exc:
        logger.error("input type not defined: %s", exc)
    registry = get_prompt_registry()
    if event_type == "Market Complaint":
        user_prompt = registry.get("ps_evaluation/pse_mc").format(query=query, event_type=event_type)
    else:
        user_prompt = registry.get("ps_evaluation/pse_non_mc").format(query=query, event_type=event_type)
    try:
        response = await llm.get_structured_response(system_prompt=(registry.get("ps_evaluation/system") + registry.get("guardrail")), user_prompt=user_prompt, structure=CheckList)
        
        checklist_model: CheckList = response
        checklist_dict = checklist_model.model_dump()
        response = checklist_dict["response"]

        return {"checklist": response}
    
    except Exception as exc:
        logger.error("checklist generation failed: %s", exc)
        return {
            "error": "Unable to generate checklists for problem statement"
        }

async def improvement_suggestion(
        state: PseState
):
    try:
        event_type = state.get("event_type", "")
        query = state.get("query", "")
        check_list_data = state.get("checklist", [])
        registry = get_prompt_registry()
        if event_type == "Market Complaint":
            user_prompt = registry.get("ps_evaluation/mc_improvement").format(query=query, event_type=event_type, checklist=check_list_data)
        else:
            user_prompt = registry.get("ps_evaluation/non_mc_improvement").format(query=query, event_type=event_type, checklist=check_list_data)
        response = await llm.get_structured_response(system_prompt=registry.get("ps_evaluation/system"), user_prompt=user_prompt, structure=ImprovementSuggestionList)
        return {"suggestions": response}
    
    except Exception as exc:
        logger.error("checklist generation failed: %s", exc)
        return {
            "error": "Unable to generate suggestions for problem statement"
        }


    

async def generate_immediate_actions(
        state: ActionsState
):
    try:
        event_type = state.get("event_type","")
        query = state.get("query", "")
        if event_type not in SOP_BY_EVENT_TYPE:
            raise ValueError(f"event_type must be one of: {', '.join(SOP_BY_EVENT_TYPE.keys())}")
        sops = SOP_BY_EVENT_TYPE[event_type]
        registry = get_prompt_registry()
        user_prompt = registry.get("ps_evaluation/immediate_actions_user").format(event_type=event_type,
                                                           problem_statement=query,
                                                           sop_list=sops)
        response = await llm.get_structured_response(system_prompt=registry.get("ps_evaluation/immediate_actions_system"),
                                                      user_prompt=user_prompt, structure=LLMActions)
        
        actions: list[str] = response.llm_actions

        assert isinstance(actions, list) and all(isinstance(x, str) for x in actions)

        return {"event_type":event_type,
                "sop_actions": sops,
                "llm_actions": actions}
    except Exception as exc:
        logger.error(f"error generating immediate actions in node, {exc}")
        raise ValueError("Unable to generate immediate actions for problem statement") from exc



    
