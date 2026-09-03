"""
Semantic search implementation utilizing PostgreSQL pgvector extension for cosine similarity.
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path
from typing import Any, Literal

# Inject project root to Python path for loading configs
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

import asyncpg
import numpy as np
from config.settings import settings
from src.agents.search_agent.api.services.filters import SearchFilters, build_filter_clause

search_logger = logging.getLogger(__name__)

# Mapping from friendly names to physical vector column names
TARGET_VECTOR_MAP: dict[str, str] = {
    "description": settings.COLUMN_DESCRIPTION_VECTOR,
    "root_cause_summary": settings.COLUMN_ROOT_CAUSE_VECTOR, }


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


async def semantic_search(
    pool: asyncpg.Pool,
    query_vector: list[float],
    search_field: Literal["description", "root_cause_summary"],
    filters: SearchFilters,
    limit: int = 50000,
) -> list[dict[str, Any]]:
    """
    Execute vector similarity lookups on the requested table column.
    Uses cosine distance (<=> operator) mapped to a relevance score (1 - distance).
    All table metadata is returned minus filtered-out columns.
    """
    target_vec_column = TARGET_VECTOR_MAP[search_field]

    # Dynamically build filter constraints (offset by 1 because $1 is the query vector)
    search_conditions = build_filter_clause(filters, param_offset=1)
    limit_parameter_index = 2 + len(search_conditions.params)

    # Vector columns only ever live on the vector table (aliased "v" when a
    # details table is joined in, "t" otherwise — see _build_from_clause).
    vec_table_alias = "v" if settings.SEARCH_DETAILS_TABLE else "t"
    escaped_vec_column = f'{vec_table_alias}."{target_vec_column}"'

    # Perform standard vector search with an appended relevance_score metric.
    # ORDER BY relevance_score DESC alone has no tiebreaker for rows with an
    # identical (or floating-point-identical) score — Postgres makes no
    # ordering guarantee for ties, so which exact rows land inside LIMIT can
    # genuinely vary between otherwise-identical executions of this same
    # query (confirmed live, 2026-09-03: repeated identical History Review
    # searches on the same record returned different candidate sets —
    # sometimes a real historical match, sometimes none). Appending the id
    # column as a stable secondary sort key makes row order, and therefore
    # which rows survive LIMIT, fully deterministic for identical input.
    query_sql = f"""
        SELECT
            t.*,
            (1 - ({escaped_vec_column}::vector <=> $1::vector)) AS relevance_score
        {_build_from_clause()}
        WHERE {escaped_vec_column} IS NOT NULL
            {search_conditions.sql}
        ORDER BY relevance_score DESC, t."{settings.COLUMN_ID}" ASC
        LIMIT ${limit_parameter_index}
    """

    numpy_query_vector = np.array(query_vector, dtype=np.float32)
    sql_arguments: list[Any] = [numpy_query_vector, *search_conditions.params, limit]

    search_logger.debug("vector search query executing: %s | arguments: %d", query_sql, len(sql_arguments))

    async with pool.acquire() as connection:
        query_results = await connection.fetch(query_sql, *sql_arguments)

    columns_to_hide = settings.excluded_columns_list
    
    # Build result dictionary avoiding excluded columns and embedding match metadata
    results = []
    for record in query_results:
        filtered_record = {key: val for key, val in dict(record).items() if key not in columns_to_hide}
        filtered_record["match_type"] = "semantic"
        filtered_record["matched_field"] = search_field
        results.append(filtered_record)
        
    return results
