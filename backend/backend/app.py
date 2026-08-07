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
from backend.routers.task_critique import router as task_critique_router

logger = logging.getLogger(__name__)

# Response header carrying a freshly re-issued token (sliding expiry — see
# the request_lifecycle middleware below) — must be in CORS's expose_headers
# or the frontend's fetch() can't read it at all despite it being present on
# the wire.
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
        # Without this, the browser silently discards X-Refreshed-Token —
        # allow_headers governs REQUEST headers, exposing a custom RESPONSE
        # header to frontend JS needs this separate list.
        expose_headers=[_REFRESHED_TOKEN_HEADER],
    )

    @app.middleware("http")
    async def request_lifecycle(request: Request, call_next):
        """Two things per request, both best-effort (never break the actual
        response over either): (1) sliding-expiry token refresh — a request
        made with a still-valid token gets a freshly re-issued one back (new
        full expiry window) via _REFRESHED_TOKEN_HEADER, so an active user's
        session keeps extending instead of hard-expiring exactly
        JWT_EXPIRE_MINUTES after login regardless of activity (per the user,
        2026-07-31); (2) records the call in athena_api_call_trails."""
        start = time.monotonic()
        response = await call_next(request)

        user_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            payload = try_decode_payload(auth_header[7:])
            if payload:
                user_id = payload.get("uid")
                if user_id is not None:
                    # payload["username"], NOT payload["sub"] — sub is now a
                    # UUID derived from uid (see routers/auth.py's module
                    # docstring), not the username. Also carry roles/name
                    # forward — without this, every sliding refresh would
                    # silently drop them (issue_token's params default to
                    # none/derived), regressing the feedback service's
                    # attribution back to a guessed name the moment a token
                    # first refreshes after login.
                    response.headers[_REFRESHED_TOKEN_HEADER] = issue_token(
                        payload["username"], user_id, payload.get("roles"), payload.get("name")
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
    # /auth/login obviously can't require a token to get one; /auth/me
    # self-protects internally (see routers/auth.py). Every other router
    # requires a valid JWT — the frontend already sends one on every request.
    app.include_router(health_router, prefix=api_prefix)
    app.include_router(auth_router, prefix=api_prefix)
    protected = {"dependencies": [Depends(get_current_username)]}
    app.include_router(problem_statement_router, prefix=api_prefix, **protected)
    app.include_router(evidence_router, prefix=api_prefix, **protected)
    app.include_router(questionnaire_router, prefix=api_prefix, **protected)
    app.include_router(rci_plan_router, prefix=api_prefix, **protected)
    app.include_router(task_critique_router, prefix=api_prefix, **protected)
    app.include_router(rc_capa_critique_router, prefix=api_prefix, **protected)
    app.include_router(action_center_router, prefix=api_prefix, **protected)
    app.include_router(analytics_router, prefix=api_prefix, **protected)

    return app
