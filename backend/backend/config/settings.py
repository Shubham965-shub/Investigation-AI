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
    # Short connect timeout fails fast on a down ds; read gets more room for long-running calls.
    DS_SERVICE_CONNECT_TIMEOUT_SECONDS: float = 10.0
    DS_SERVICE_READ_TIMEOUT_SECONDS: float = 120.0
    # Critique/scoring endpoints are multi-LLM-call (scoring can fire ~20 concurrent calls) so they need a longer timeout.
    # Kept comfortably under Azure Container Apps' platform-level ingress request timeout
    # (240s default) — at 300s, a slow-but-eventually-successful DS scoring call (task report
    # upload's /score/report) could get killed by the platform before the backend ever responds,
    # producing a raw network failure with no error detail on the frontend instead of a real
    # timeout error message. 200s leaves headroom on both sides.
    DS_SERVICE_HEAVY_READ_TIMEOUT_SECONDS: float = 200.0

    # ── CORS (comma-separated origins) ───────────────────────
    CORS_ORIGINS: str = "http://localhost:5173"

    # ── Auth (JWT) ──
    # JWT_SECRET is a PLATFORM-WIDE shared secret (matches the ARGUS Lighthouse JwtService), not just this backend's own.
    JWT_SECRET: str = "dev-placeholder-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # ── Event Explorer SSO handoff ────
    # Dedicated secret for InvestigationAI_BE handoff — deliberately not JWT_SECRET, so a leak can't forge a real session elsewhere.
    EVENT_EXPLORER_HANDOFF_SECRET: str = "dev-placeholder-handoff-secret-change-me"
    EVENT_EXPLORER_URL: str = "https://ashy-field-01d0ebc00.7.azurestaticapps.net"

    # ── Database (same shared Postgres instance InvestigationAi_DS uses) ──
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "investigation_ai"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_POOL_MIN_SIZE: int = 1
    DB_POOL_MAX_SIZE: int = 10
    # Takes precedence over DB_HOST/PORT/NAME/USER/PASSWORD when set.
    DATABASE_URL_OVERRIDE: Optional[str] = None

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def DATABASE_URL(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        # safe="" so special chars in user/password aren't misparsed as URL structure.
        user = quote(self.DB_USER, safe="")
        password = quote(self.DB_PASSWORD, safe="")
        return f"postgresql://{user}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
