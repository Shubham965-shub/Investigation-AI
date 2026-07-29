"""
API Application factory module managing FastAPI lifespan and routers.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.utils import deps
from src.agents.search_agent.api.routes.search_route import router as router_search
from agents.problem_statement_evaluation.api.routes.ps_route import router as router_pse
from agents.problem_statement_evaluation.v2.routes.ps_v2_route import router as router_pse_v2
from src.agents.critique.api.routes.critique_route import router as router_critique
from src.agents.critique.api.routes.questionnaire_route import router as router_questionnaire
from src.agents.search_agent.api.routes.rc_synthesizer_route import router as router_rc_synthesizer
from src.agents.search_agent.api.routes.capa_synthesizer_route import router as router_capa_synthesizer
from src.agents.search_agent.api.routes.event_synthesizer_route import router as router_er_synthesizer
from src.agents.rot_cause_advisor.api.routes.root_cause_advisor_route import router as router_rot_cause_advisor
from src.agents.evidence_collection.routes import router as router_evidence
from src.agents.interview_questionnaire.routes import router as router_questionnaire_iq
from src.agents.rci_plan.routes import router as router_rci_plan
from src.agents.critique.api.routes.task_report_critique_route import router as router_task_report_critique
from src.agents.archetypes.routes import router as router_archetypes
from src.agents.capa_depth_effectiveness.api.routes.capa_depth_effectiveness_route import (
    router as router_capa_depth_effectiveness,
)
from src.prompt_registry.service import PromptRegistry
from src.prompt_registry.routes import router as router_prompts
from src.db.pool import close_pool, create_pool
from src.llm.client import LLMClient

api_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle hook for managing database connections and LLM dependencies."""
    api_logger.info("Initializing application dependencies: Database Pool, LLM Client & Prompt Registry")
    db_pool = await create_pool()
    llm_instance = LLMClient()
    prompt_registry = PromptRegistry()
    prompt_registry.setup()

    deps.set_pool(db_pool)
    deps.set_llm(llm_instance)
    deps.set_prompt_registry(prompt_registry)

    yield  # Hand control back to FastAPI app

    api_logger.info("Tearing down application dependencies: Closing Database Pool")
    await close_pool(db_pool)


def create_app() -> FastAPI:
    """Constructs and returns the mounted FastAPI instance."""
    api_instance = FastAPI(
        title="Agentic Search Service",
        description=(
            "LangGraph-backed inference API integrating keyword and semantic "
            "search methodologies with AI reranking mechanisms."
        ),
        version="0.2.0",
        lifespan=lifespan,
    )

    api_instance.include_router(router_search)
    api_instance.include_router(router_pse)
    api_instance.include_router(router_pse_v2)
    api_instance.include_router(router_critique)
    api_instance.include_router(router_rc_synthesizer)
    api_instance.include_router(router_capa_synthesizer)
    api_instance.include_router(router_questionnaire)
    api_instance.include_router(router_er_synthesizer)
    api_instance.include_router(router_rot_cause_advisor)
    api_instance.include_router(router_evidence)
    api_instance.include_router(router_questionnaire_iq)
    api_instance.include_router(router_prompts)
    api_instance.include_router(router_rci_plan)
    api_instance.include_router(router_task_report_critique)
    api_instance.include_router(router_archetypes)
    api_instance.include_router(router_capa_depth_effectiveness)

    return api_instance
