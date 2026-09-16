"""FastAPI application factory: mounts routers, CORS and the DS HTTP client lifespan."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.clients.db_client import close_pool, create_pool
from backend.clients.ds_client import close_client, create_client
from backend.config.settings import settings
from backend.db.auth_queries import record_api_call
from backend.routers.action_center import router as action_center_router
from backend.routers.analytics import router as analytics_router
from backend.routers.auth import get_current_username, issue_token, try_decode_payload
from backend.routers.auth import router as auth_router
from backend.routers.evidence import router as evidence_router
from backend.routers.health import router as health_router
from backend.routers.problem_statement import router as problem_statement_router
from backend.routers.questionnaire import router as questionnaire_router
from backend.routers.rc_capa_critique import router as rc_capa_critique_router
from backend.routers.rci_plan import router as rci_plan_router
from backend.routers.rci_report import router as rci_report_router
from backend.routers.task_critique import router as task_critique_router

logger = logging.getLogger(__name__)

# Must be in CORS's expose_headers or the frontend's fetch() can't read it despite it being on the wire.
_REFRESHED_TOKEN_HEADER = "X-Refreshed-Token"


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
        # allow_headers only covers request headers; exposing a response header to JS needs this separately.
        expose_headers=[_REFRESHED_TOKEN_HEADER],
    )

    @app.middleware("http")
    async def request_lifecycle(request: Request, call_next):
        """Best-effort: refreshes the token (sliding expiry) and logs the call to athena_api_call_trails."""
        start = time.monotonic()
        response = await call_next(request)

        user_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            payload = try_decode_payload(auth_header[7:])
            if payload:
                user_id = payload.get("uid")
                if user_id is not None:
                    # sub is a UUID derived from uid, not the username; must carry roles/name/investigator_name forward or a refresh silently drops them.
                    response.headers[_REFRESHED_TOKEN_HEADER] = issue_token(
                        payload["username"],
                        user_id,
                        payload.get("roles"),
                        payload.get("name"),
                        payload.get("investigator_name"),
                    )

        try:
            await record_api_call(
                user_id,
                request.method,
                request.url.path,
                response.status_code,
                int((time.monotonic() - start) * 1000),
                request.client.host if request.client else None,
            )
        except Exception:
            logger.warning("Could not record API call trail", exc_info=True)

        return response

    api_prefix = "/api"
    # /auth/login and /auth/me are unprotected here; /auth/me self-protects internally.
    app.include_router(health_router, prefix=api_prefix)
    app.include_router(auth_router, prefix=api_prefix)
    protected = {"dependencies": [Depends(get_current_username)]}
    app.include_router(problem_statement_router, prefix=api_prefix, **protected)
    app.include_router(evidence_router, prefix=api_prefix, **protected)
    app.include_router(questionnaire_router, prefix=api_prefix, **protected)
    app.include_router(rci_plan_router, prefix=api_prefix, **protected)
    app.include_router(task_critique_router, prefix=api_prefix, **protected)
    app.include_router(rc_capa_critique_router, prefix=api_prefix, **protected)
    app.include_router(rci_report_router, prefix=api_prefix, **protected)
    app.include_router(action_center_router, prefix=api_prefix, **protected)
    app.include_router(analytics_router, prefix=api_prefix, **protected)

    return app
