"""Application settings loaded from environment variables / .env."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration for the product-facing backend."""

    # ── Server ────────────────────────────────────────────────
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # ── Upstream InvestigationAi_DS service ──────────────────
    DS_SERVICE_BASE_URL: str = "http://localhost:8001"
    DS_SERVICE_TIMEOUT_SECONDS: float = 60.0

    # ── CORS (comma-separated origins) ───────────────────────
    CORS_ORIGINS: str = "http://localhost:5173"

    # ── Auth placeholder ──────────────────────────────────────
    AUTH_PLACEHOLDER_SECRET: str = "dev-placeholder-secret-change-me"

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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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
