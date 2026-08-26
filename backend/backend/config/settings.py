"""Application settings loaded from environment variables / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ (this file lives at backend/config/settings.py)
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Environment-driven configuration for the product-facing backend."""

    # ── Server ────────────────────────────────────────────────
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # ── Upstream InvestigationAi_DS service ──────────────────
    DS_SERVICE_BASE_URL: str = "http://localhost:8001"
    # Split connect/read (2026-08-26, per the user) — a short connect timeout
    # still fails fast when ds is genuinely down, while read gets much more
    # room since real ds calls (critique, scoring) can legitimately run long.
    # See clients/ds_client.py for how these compose into the default and
    # heavy per-call timeouts.
    DS_SERVICE_CONNECT_TIMEOUT_SECONDS: float = 10.0
    DS_SERVICE_READ_TIMEOUT_SECONDS: float = 120.0
    # Confirmed via read-only ds research (2026-08-26): /critique/analyse-task-report,
    # RC/CAPA's critique endpoints, and /score/report are all multi-LLM-call
    # operations (scoring alone can fire ~20 concurrent calls per request) —
    # they get a much longer read timeout than the lightweight generation
    # endpoints (/ps/v2/generate, /rci/plan).
    DS_SERVICE_HEAVY_READ_TIMEOUT_SECONDS: float = 300.0

    # ── CORS (comma-separated origins) ───────────────────────
    CORS_ORIGINS: str = "http://localhost:5173"

    # ── Auth (JWT) — still no real credential store (see routers/auth.py),
    # but tokens are now real signed/expiring JWTs, not an opaque placeholder.
    #
    # JWT_SECRET is a PLATFORM-WIDE shared secret, not just this backend's own
    # — confirmed 2026-08-03 by checking the reference ARGUS Lighthouse repo
    # (Strides-Pharma-Science-Ltd/Lab-Error-Platform): its Java/Quarkus
    # JwtService docstring says "set a >=256-bit JWT_SECRET in deployment for
    # interoperability with the FastAPI tokens" — i.e. one secret across every
    # app AND the separate feedback service, so any app's own regular session
    # token is already valid everywhere. There is no separate per-service
    # token to mint (an earlier attempt at that here was wrong — see git
    # history). See issue_token()'s `roles` claim for the other half of that
    # interoperability contract.
    JWT_SECRET: str = "dev-placeholder-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # ── Event Explorer SSO handoff (2026-08-19, per the user) ────
    # InvestigationAI_BE/_FE are a separate, parallel backend+frontend stack
    # for the same product (see routers/rci_plan.py's "View Historic Data"
    # button — "Explore Events" opens InvestigationAI_FE's Event Explorer at
    # EVENT_EXPLORER_URL). EVENT_EXPLORER_HANDOFF_SECRET is a DEDICATED
    # secret shared only with InvestigationAI_BE — deliberately NOT the same
    # as JWT_SECRET (that one is the platform-wide session-token secret
    # shared with the feedback service and others; reusing it here would
    # mean a leaked handoff token could forge a real, long-lived session
    # anywhere else too). This secret only ever signs short-lived,
    # single-purpose handoff tokens minted by the new
    # /auth/event-explorer-handoff endpoint and verified by
    # InvestigationAI_BE's matching SSO-exchange endpoint.
    EVENT_EXPLORER_HANDOFF_SECRET: str = "dev-placeholder-handoff-secret-change-me"
    EVENT_EXPLORER_URL: str = "https://ashy-field-01d0ebc00.7.azurestaticapps.net"

    # ── Database (same shared Postgres instance InvestigationAi_DS uses —
    # hosts this backend's auth tables (users/roles/api_call_trails) plus
    # the STAR schema (FACT_QMS_EVENTS + dimensions), not a separate DB) ──
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "investigation_ai"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_POOL_MIN_SIZE: int = 1
    DB_POOL_MAX_SIZE: int = 10
    # If set, takes precedence over the DB_HOST/PORT/NAME/USER/PASSWORD parts
    # above — convenient when a DB owner hands over one connection string
    # rather than discrete pieces.
    DATABASE_URL_OVERRIDE: Optional[str] = None

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def DATABASE_URL(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        # quote(..., safe="") so special characters in user/password (#, @, /,
        # etc.) can't be misparsed as URL structure (userinfo delimiter,
        # fragment marker, ...).
        user = quote(self.DB_USER, safe="")
        password = quote(self.DB_PASSWORD, safe="")
        return f"postgresql://{user}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
