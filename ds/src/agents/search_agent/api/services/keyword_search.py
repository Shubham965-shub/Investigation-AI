"""
PostgreSQL full-text keyword search implementation utilizing tsvector and tsquery.
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path
from typing import Any, Literal

# Inject project root path for configuration loading
PROJECT_ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT_DIR))

import asyncpg
from config.settings import settings
from src.agents.search_agent.api.services.filters import SearchFilters, build_filter_clause
from src.utils.text import extract_search_terms

kw_logger = logging.getLogger(__name__)

# Dictionary correlating application field names to physical DB columns
TARGET_SEARCH_FIELDS: dict[str, str] = {
    "description": settings.COLUMN_DESCRIPTION,
    "root_cause_summary": settings.COLUMN_ROOT_CAUSE,
}


def build_tsquery_format(raw_input: str, max_terms: int = 0) -> str:
    """
    Transforms plain text into a valid PostgreSQL ``tsquery`` structured format.

    Uses alphanumeric token extraction (not whitespace-split + naive join)
    so punctuation, batch-number fragments, percentages, brackets, and
    hyphenated compounds in ``raw_input`` can never produce invalid tsquery
    syntax. ``max_terms=0`` (default) applies no cap here — term-count
    policy belongs to the caller; this function's only job is validity.
    """
    terms = extract_search_terms(raw_input, max_terms=max_terms or 0)
    if not terms:
        return ""
    return " & ".join(terms)


def _build_from_clause() -> str:
    """Build the FROM clause, joining the vector table to the details table when configured.

    ``SEARCH_TABLE`` holds only description/root_cause_summary text plus their
    embeddings; ``SEARCH_DETAILS_TABLE`` (when set) holds the full event metadata
    (qe_type, location, date_opened, etc.). They're joined on (id, secondary_key)
    so callers get the full record rather than just the 6 vector-table columns.
    """
    if settings.SEARCH_DETAILS_TABLE:
        return (
            f'FROM "{settings.SEARCH_DETAILS_TABLE}" t '
            f'JOIN "{settings.SEARCH_TABLE}" v '
            f'ON t."{settings.COLUMN_ID}" = v."{settings.COLUMN_ID}" '
            f'AND t."{settings.JOIN_SECONDARY_KEY}" = v."{settings.JOIN_SECONDARY_KEY}"'
        )
    return f'FROM "{settings.SEARCH_TABLE}" t'


async def keyword_search(
    pool: asyncpg.Pool,
    query: str,
    search_field: Literal["description", "root_cause_summary"],
    filters: SearchFilters,
    limit: int = 50000,
) -> list[dict[str, Any]]:
    """
    Execute a full-text lookup against a defined target field.

    Applies dynamic ``to_tsvector`` functionality dynamically across texts
    allowing schema adaptability without pre-indexed columns.
    Results are strictly sorted by date, bypassing relevance scores.
    """
    formatted_tsquery = build_tsquery_format(query)
    if not formatted_tsquery:
        return []

    # Map target physical column
    db_text_col = TARGET_SEARCH_FIELDS[search_field]

    # Dynamically build filter constraints (offset by 1 since query string occupies $1)
    condition_clause = build_filter_clause(filters, param_offset=1)
    limit_param_index = 2 + len(condition_clause.params)

    # Perform TS search prioritizing descending date sorting
    search_sql = f"""
        SELECT
            t.*,
            ts_rank_cd(to_tsvector('english', t."{db_text_col}"), query_t) AS relevance_score
        {_build_from_clause()},
             to_tsquery('english', $1) AS query_t
        WHERE to_tsvector('english', t."{db_text_col}") @@ query_t
            {condition_clause.sql}
        ORDER BY t."{settings.COLUMN_DATE_OPENED}" DESC
        LIMIT ${limit_param_index}
    """

    sql_args: list[Any] = [formatted_tsquery, *condition_clause.params, limit]

    kw_logger.debug("Executing keyword search sql: %s | with %d parameters", search_sql, len(sql_args))

    async with pool.acquire() as db_conn:
        query_rows = await db_conn.fetch(search_sql, *sql_args)

    columns_to_omit = settings.excluded_columns_list
    
    # Process return data shaping
    output_records = []
    for raw_row in query_rows:
        record = {k: v for k, v in dict(raw_row).items() if k not in columns_to_omit}
        record["match_type"] = "keyword"
        record["matched_field"] = search_field
        output_records.append(record)
        
    return output_records
