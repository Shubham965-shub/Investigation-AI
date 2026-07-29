"""Shared application settings for all agents.

Configuration is split into two sources:
- .env: Secrets and environment-specific values (DB credentials, API keys, server)
- config/config.yaml: Schema mappings and structural config (tables, columns, limits)

The unified `settings` object exposes all values with the same attribute names
as before, so consumers do not need to change.
"""
from pathlib import Path
from urllib.parse import quote

import yaml
from pydantic_settings import BaseSettings

# Project root directory (InvestigationAI/)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Path to config (version-controlled)
CONFIG_PATH = PROJECT_ROOT/"src"/"config"/"config.yaml"


class EnvSettings(BaseSettings):
    """Secrets and environment-specific config loaded from .env."""

    # ── Database ────────────────────────────────────────────
    DB_HOST: str
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_PORT: int
    DB_POOL_MIN_SIZE: int
    DB_POOL_MAX_SIZE: int

    # ── OpenAI (secret) ─────────────────────────────────────
    OPENAI_API_KEY: str

    # ── Server ──────────────────────────────────────────────
    SEARCH_AGENT_HOST: str
    SEARCH_AGENT_PORT: int

    # ── Celery / Redis ───────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


def _load_schema() -> dict:
    """Load schema and structural config from YAML."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config not found at {CONFIG_PATH}. "
            "Ensure config/config.yaml exists."
        )
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class SharedSettings:
    """
    Unified settings combining .env (secrets/env) and config.yaml (structural config).
    Exposes the same attribute names as before for backward compatibility.
    """

    def __init__(self) -> None:
        self._env = EnvSettings()
        self._schema = _load_schema()

        # Tables
        t = self._schema.get("tables", {})
        sc = t.get("summary_columns", {})
        self.SEARCH_TABLE = t.get("search", "")
        self.SUMMARY_TABLE = t.get("summary", "")
        self.SUMMARY_ID_COLUMN = t.get("summary_id_column", "")
        self.SUMMARY_COL_EVENT_DESCRIPTION = sc.get("event_description", "")
        self.SUMMARY_COL_ROOT_CAUSE = sc.get("rc_summary_summary", "")
        self.SUMMARY_COL_CAPA = sc.get("capa", "")
        self.SUMMARY_COL_CAPA_DATE = sc.get("capa_date", "")
        # Columns
        c = self._schema.get("columns", {})
        self.COLUMN_ID = c.get("id", "")
        self.COLUMN_DESCRIPTION = c.get("description", "")
        self.COLUMN_ROOT_CAUSE = c.get("root_cause", "")
        self.COLUMN_CATEGORY = c.get("category", "")
        self.COLUMN_DATE_OPENED = c.get("date_opened", "")
        self.COLUMN_QE_TYPE = c.get("qe_type", "")
        self.COLUMN_LOCATION = c.get("location", "")
        self.COLUMN_INSTRUMENT = c.get("instrument", "")
        self.COLUMN_MATERIAL = c.get("material", "")
        self.COLUMN_DESCRIPTION_TSV = c.get("description_tsv", "")
        self.COLUMN_ROOT_CAUSE_TSV = c.get("root_cause_tsv", "")
        self.COLUMN_DESCRIPTION_VECTOR = c.get("description_vector", "")
        self.COLUMN_ROOT_CAUSE_VECTOR = c.get("root_cause_vector", "")
        self.COLUMN_CAPA_NUMBER = c.get("capa_number", "")
        self.COLUMN_IMMEDIATE_ACTIONS = c.get("immediate_actions", "")
        self.COLUMN_CORRECTIVE_ACTIONS = c.get("corrective_actions", "")
        self.COLUMN_PREVENTIVE_ACTIONS = c.get("preventive_actions", "")
        self.COLUMN_SFG_CODE = c.get("sfg_code", "")
        self.COLUMN_CAPA_IMPLEMENTATION_DATE = c.get("capa_implementation_date", "")
        self.COLUMN_SUMMARY_CAPA_DATE = c.get("capa_date", "")

        
        # Exclude columns (stored as list in YAML)
        excl = self._schema.get("exclude_columns", [])
        self.EXCLUDE_COLUMNS = ",".join(excl) if isinstance(excl, list) else str(excl)

        # Search limits
        s = self._schema.get("search", {})
        self.KEYWORD_SEARCH_LIMIT = s.get("keyword_limit", 50000)
        self.SEMANTIC_SEARCH_LIMIT = s.get("semantic_limit", 150)
        # self.RERANK_TOP_K = s.get("rerank_top_k", 20)
        self.FINAL_TOP_K = s.get("final_top_k", 10)
        self.SEMANTIC_RELEVANCE_TRESHLOD =s.get("relevance_treshold", 0.5)


        # Worker dispatcher settings
        w = self._schema.get("workers", {})
        self.WORKER_N_WORKERS: int = w.get("n_workers", 3)
        self.WORKER_RPM_LIMIT: int = w.get("rpm_limit", 15)
        self.WORKER_PG_CHANNEL: str = w.get("pg_channel", "deviation_inserted")

        # OpenAI model config (from schema)
        o = self._schema.get("openai", {})
        self.OPENAI_MODEL = o.get("model", "gpt-5.4-mini")
        self.OPENAI_EMBEDDING_MODEL = o.get("embedding_model", "text-embedding-3-large")
        self.EMBEDDING_DIMENSIONS = o.get("embedding_dimensions", 3072)

        # LLM
        llm = self._schema.get("llm", {})
        self.LLM_TEMPERATURE = llm.get("temperature", 0.0)

    # ── From .env (secrets + environment) ────────────────────

    @property
    def DB_HOST(self) -> str:
        return self._env.DB_HOST

    @property
    def DB_NAME(self) -> str:
        return self._env.DB_NAME

    @property
    def DB_USER(self) -> str:
        return self._env.DB_USER

    @property
    def DB_PASSWORD(self) -> str:
        return self._env.DB_PASSWORD

    @property
    def DB_PORT(self) -> int:
        return self._env.DB_PORT

    @property
    def DB_POOL_MIN_SIZE(self) -> int:
        return self._env.DB_POOL_MIN_SIZE

    @property
    def DB_POOL_MAX_SIZE(self) -> int:
        return self._env.DB_POOL_MAX_SIZE

    @property
    def OPENAI_API_KEY(self) -> str:
        return self._env.OPENAI_API_KEY

    @property
    def SEARCH_AGENT_HOST(self) -> str:
        return self._env.SEARCH_AGENT_HOST

    @property
    def SEARCH_AGENT_PORT(self) -> int:
        return self._env.SEARCH_AGENT_PORT

    @property
    def REDIS_URL(self) -> str:
        return self._env.REDIS_URL

    # ── Computed properties ──────────────────────────────────

    @property
    def excluded_columns_list(self) -> list[str]:
        """Parse EXCLUDE_COLUMNS into a list, handling empty values."""
        if not self.EXCLUDE_COLUMNS:
            return []
        return [col.strip() for col in self.EXCLUDE_COLUMNS.split(",") if col.strip()]

    @property
    def DATABASE_URL(self) -> str:
        """Construct PostgreSQL connection URL.

        User/password are percent-encoded (safe="") since credentials may
        contain characters like '#' or '@' that would otherwise be
        misinterpreted as URL delimiters (e.g. '#' truncating the DSN as a
        fragment marker, corrupting the host/port that follow it).
        """
        user = quote(self._env.DB_USER, safe="")
        password = quote(self._env.DB_PASSWORD, safe="")
        return (
            f"postgresql://{user}:{password}"
            f"@{self._env.DB_HOST}:{self._env.DB_PORT}/{self._env.DB_NAME}"
        )

    @property
    def PROMPTS_DIR(self) -> Path:
        """Return path to centralized prompts directory."""
        return PROJECT_ROOT / "src" / "prompts"


# Singleton instance
settings = SharedSettings()
