"""
Node implementations for the agentic search graph.

Each function takes the current ``SearchState`` and returns an updated copy.
Side-effect dependencies (DB pool, LLM client) are injected via closures in
``builder.py``.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import asyncpg

from src.agents.search_agent.graph.state import SearchState
from src.llm.client import LLMClient
from src.agents.search_agent.api.services.filters import SearchFilters
from src.agents.search_agent.api.services.keyword_search import keyword_search
from src.agents.search_agent.api.services.semantic_search import semantic_search
from src.config.settings import settings

logger = logging.getLogger(__name__)


# ── Prompt Loading ──────────────────────────────────────────

def _load_prompt(filename: str) -> str:
    """Load a prompt template from the centralized prompts directory."""
    if filename == "guardrail.txt":
        prompt_path = settings.PROMPTS_DIR / filename
        return prompt_path.read_text(encoding="utf-8")
    prompt_path = settings.PROMPTS_DIR / "search_agent" / filename
    return prompt_path.read_text(encoding="utf-8")

guard_rail_text = _load_prompt("guardrail.txt")


# ── Helpers ─────────────────────────────────────────────────

def _normalize_date(date_val):
    if date_val in ("null", None, "", "None"):
        return None

    if isinstance(date_val, str):
        return datetime.fromisoformat(date_val)
    
    if isinstance(date_val, datetime):
        return date_val

    return date_val

def _filters_from_dict(d: dict[str, Any]) -> SearchFilters:
    """Convert a raw dict to a ``SearchFilters`` dataclass."""
    qe_type = d.get("qe_type")
    date_from = d.get("date_from")
    date_to = d.get("date_to")
    locations = d.get("locations")
    instruments = d.get("instruments")
    materials = d.get("materials")
    sfg_code = d.get("sfg_code")
    exclude_id = d.get("exclude_id")

    date_from = _normalize_date(date_from)
    date_to = _normalize_date(date_to)

    return SearchFilters(
        qe_type=qe_type if qe_type not in ("null", None) else None,
        date_from=date_from,
        date_to=date_to,
        locations=locations if locations not in ("null", None) else None,
        instruments=instruments if instruments not in ("null", None) else None,
        materials=materials if materials not in ("null", None) else None,
        sfg_code=sfg_code if sfg_code not in ("null", None) else None,
        exclude_id=exclude_id if exclude_id not in ("null", None) else None,
    )


# ── Node 1: analyze_query ──────────────────────────────────


async def analyze_query(
    state: SearchState,
) -> dict[str, Any]:
    """Use GPT-4o to decide search type and extract / merge filters."""
    user_pref = (state.get("search_type") or "auto").lower()

    if user_pref in ("keyword", "semantic"):
        determined = user_pref
    else:
        determined = "hybrid"

    return {
        "determined_search_type": determined,
        "filters": state.get("filters", {}),
    }


# ── Node 2: keyword_search_node ────────────────────────────


async def keyword_search_node(
    state: SearchState,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    """Execute full-text keyword search on the user-selected field(s)."""
    
    filters = _filters_from_dict(state.get("filters", {}))
    search_fields = state.get("search_fields", ["description"])

    all_results = []
    logger.info(f"entered key word search")

    # Search each field separately
    for field in search_fields:
        try:
            field_results = await keyword_search(
                pool=pool,
                query=state["query"],
                search_field=field,
                filters=filters,
#                limit=settings.KEYWORD_SEARCH_LIMIT,
            )
            all_results.extend(field_results)
        except Exception as exc:
            logger.error("keyword_search_node failed for field %s: %s", field, exc)

    # Deduplicate by ID (keep highest score if duplicate)
    # Use the dynamic ID column name from settings
    id_col = settings.COLUMN_ID
    seen = {}
    for result in all_results:
        result_id = result.get(id_col) or result.get("id")  # Fallback to lowercase
        if result_id and (result_id not in seen or result["relevance_score"] > seen[result_id]["relevance_score"]):
            seen[result_id] = result

    deduplicated_results = list(seen.values())
    logger.info(f"{len(deduplicated_results)} key word search results:")

    # Sort by relevance score descending
    deduplicated_results.sort(key=lambda x: x["relevance_score"], reverse=True)

    return {"keyword_results": deduplicated_results}


# ── Node 3: semantic_search_node ────────────────────────────
def _adaptive_semantic_threshold(query: str, base: float) -> float:
    """Dynamically adjust semantic relevance threshold based on query complexity."""
    word_count = len(query.strip().split())
    if word_count <= 3:
        return min(base + 0.15, 0.75)  
    elif word_count >= 15:
        return max(base - 0.10, 0.35)
    return base 


async def semantic_search_node(
    state: SearchState,
    pool: asyncpg.Pool,
    llm: LLMClient,
) -> dict[str, Any]:
    """Generate query embedding then run vector similarity search on selected field(s)."""
    filters = _filters_from_dict(state.get("filters", {}))
    search_fields = state.get("search_fields", ["description"])
    all_results = []
    query = state["query"]
    min_relevance = 0.5
    print(f"Semantic relevance threshold set to {min_relevance:.2f} for query: {query!r}")
    logger.info(f"entered semantic search")

    try:
        query_vector = await llm.embed_text(query)
        
        # Search each field separately
        for field in search_fields:
            try:
                field_results = await semantic_search(
                    pool=pool,
                    query_vector=query_vector,
                    search_field=field,
                    filters=filters,
                    limit=settings.SEMANTIC_SEARCH_LIMIT,
                )
                filtered_field_results = [
                    result for result in field_results
                    if float(result.get("relevance_score", 0)) >= min_relevance
                ]
                all_results.extend(filtered_field_results)
            except Exception as exc:
                logger.error("semantic_search_node failed for field %s: %s", field, exc)
                
    except Exception as exc:
        logger.error("semantic_search_node embedding failed: %s", exc)

    # Deduplicate by ID (keep highest score if duplicate)
    # Use the dynamic ID column name from settings
    id_col = settings.COLUMN_ID
    seen = {}
    for result in all_results:
        result_id = result.get(id_col) or result.get("id")  # Fallback to lowercase
        if result_id and (result_id not in seen or result["relevance_score"] > seen[result_id]["relevance_score"]): # and result["relevance_score"] > treshold:
            seen[result_id] = result

    deduplicated_results = list(seen.values())
    # Sort by relevance score descending
    deduplicated_results.sort(key=lambda x: x["relevance_score"], reverse=True)
    logger.info(f"{len(deduplicated_results)} semantic search results:")

    return {"semantic_results": deduplicated_results}


# ── Node 4: combine_results ────────────────────────────────

async def combine_results_node(state: SearchState) -> dict[str, Any]:
    """Merge, deduplicate, and finalize results."""
    logger.info(f"entered combine")

    id_col = settings.COLUMN_ID
    seen: dict[Any, dict] = {}

    # Merge keyword + semantic
    all_results = (
        state.get("keyword_results", []) +
        state.get("semantic_results", [])
    )

    # Deduplicate → keep best score (IMPORTANT improvement)
    for r in all_results:
        rid = r.get(id_col) or r.get("id")
        if not rid:
            continue

        if rid not in seen or r.get("relevance_score", 0) > seen[rid].get("relevance_score", 0):
            seen[rid] = r

    final_results = list(seen.values())
    logger.info(f"final combined results count: {len(final_results)}")

    search_type = state.get("determined_search_type", "").lower()

    # Sort only for semantic / hybrid
    if search_type != "keyword":
        final_results.sort(
            key=lambda r: r.get("relevance_score", 0),
            reverse=True
        )
    return {"final_results": final_results}