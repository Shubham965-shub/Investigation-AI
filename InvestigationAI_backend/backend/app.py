"""FastAPI application factory: mounts routers, CORS and the DS HTTP client lifespan."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.clients.db_client import close_pool, create_pool
from backend.clients.ds_client import close_client, create_client
from backend.config.settings import settings
from backend.routers.action_center import router as action_center_router
from backend.routers.auth import router as auth_router
from backend.routers.evidence import router as evidence_router
from backend.routers.health import router as health_router
from backend.routers.problem_statement import router as problem_statement_router
from backend.routers.questionnaire import router as questionnaire_router
from backend.routers.rci_plan import router as rci_plan_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_client()
    await create_pool()
    yield
    await close_pool()
    await close_client()


def create_app() -> FastAPI:
    app = FastAPI(
        title="InvestigationAI Backend",
        description=(
            "Product-facing FastAPI backend for InvestigationAI. Serves the app UI "
            "and delegates all LLM/search/critique work to the InvestigationAi_DS "
            "service over HTTP."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_prefix = "/api"
    app.include_router(health_router, prefix=api_prefix)
    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(problem_statement_router, prefix=api_prefix)
    app.include_router(evidence_router, prefix=api_prefix)
    app.include_router(questionnaire_router, prefix=api_prefix)
    app.include_router(rci_plan_router, prefix=api_prefix)
    app.include_router(action_center_router, prefix=api_prefix)

    return app
