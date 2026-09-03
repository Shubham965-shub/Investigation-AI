"""
Node implementations for the agentic search graph.

Each function takes the current ``SearchState`` and returns an updated copy.
Side-effect dependencies (DB pool, LLM client) are injected via closures in
``builder.py``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from collections import OrderedDict
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
from src.agents.search_agent.api.services.relevance_filter import filter_relevant
from src.agents.search_agent.api.services.rerank import rerank_by_clean_embeddings
from src.config.settings import settings
from src.utils.deps import get_prompt_registry
from src.utils.text import sanitize_for_tsquery

# Cap on candidates judged by relevance_filter_node per search — bounds LLM
# cost to a single call regardless of how many raw candidates were found.
# rerank_candidates_node re-sorts by clean-embedding similarity first, so
# genuine matches cluster near the top instead of being scattered across the
# whole pool (confirmed: true matches moved from ranks 71-133 to ranks 1-41
# after reranking on one query/pool, and ranks 74-86 to ranks 1-17 on
# another) — 25 still missed some of a wider cluster at ranks 31-41; 50
# gives headroom above that without paying for a much larger judgment call.
_RELEVANCE_FILTER_TOP_N = 50

logger = logging.getLogger(__name__)

# Queries at/below this word count are treated as already-distilled (the
# only other producer feeding this graph, shared/build_search_query, targets
# 8-20 words per its own prompt) and skipped — raw free-text problem
# statements from the search UI ran 60-150+ words in real test data, so
# there's no realistic query landing in between; biased toward skipping to
# avoid a redundant LLM call on the historical-search fallback call sites.
_DISTILLATION_WORD_THRESHOLD = 25

# Cache of raw problem-statement text -> distilled_query. The LLM distillation
# call is not perfectly deterministic even at temperature=0 (confirmed via
# testing: the same raw text produced 3 differently-worded distillations
# across 3 calls, which in turn embedded to meaningfully different vectors
# and reshuffled the entire candidate ranking). Problem statements are
# persisted records, not one-off free text, so the same raw text is searched
# repeatedly — caching by that text guarantees identical distillation, and
# therefore identical downstream ranking, for every repeat search of the same
# investigation. Bounded to avoid unbounded growth in a long-running process
# — raised from 1000 to 8000 (2026-09-03, per the user): on a live, actively-
# used server, other unrelated concurrent searches evict LRU entries just
# like any other search would, so a repeat History Review search on the
# same record could still hit a cache miss (and a differently-worded, if
# rare, redistillation) purely from other traffic in between — a much larger
# bound makes that far less likely without meaningfully growing memory use
# (each entry is a couple of short strings).
_DISTILLED_QUERY_CACHE: "OrderedDict[str, list[str]]" = OrderedDict()
_DISTILLED_QUERY_CACHE_MAX = 8000

# Caching alone only guarantees determinism for a WARM cache entry — a cold
# or evicted one still rolls the dice on a single distillation. Generating
# this many variants per (cold) distillation and searching with all of them
# (semantic_search_node) directly reduces the odds a genuine match is missed
# because of how ANY ONE of them happened to be worded, matching this
# module's existing recall-first pattern (score-cutoff removal, relevance-
# filter judgment unioning) rather than trusting a single LLM roll.
_DISTILLATION_VARIANT_ATTEMPTS = 3


def _distilled_query_cache_get(key: str) -> list[str] | None:
    if key not in _DISTILLED_QUERY_CACHE:
        return None
    _DISTILLED_QUERY_CACHE.move_to_end(key)
    return _DISTILLED_QUERY_CACHE[key]


def _distilled_query_cache_set(key: str, value: list[str]) -> None:
    _DISTILLED_QUERY_CACHE[key] = value
    _DISTILLED_QUERY_CACHE.move_to_end(key)
    if len(_DISTILLED_QUERY_CACHE) > _DISTILLED_QUERY_CACHE_MAX:
        _DISTILLED_QUERY_CACHE.popitem(last=False)


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
    llm: LLMClient,
) -> dict[str, Any]:
    """Decide search type/filters and, for long raw free-text queries only,
    distill a mechanism-level retrieval phrase into `distilled_query`.

    Short queries (e.g. already-distilled phrases from the historical-search
    fallback callers) are left untouched — see _DISTILLATION_WORD_THRESHOLD.
    """
    user_pref = (state.get("search_type") or "auto").lower()

    if user_pref in ("keyword", "semantic"):
        determined = user_pref
    else:
        determined = "hybrid"

    result: dict[str, Any] = {
        "determined_search_type": determined,
        "filters": state.get("filters", {}),
    }

    raw_query = state.get("query", "") or ""
    if len(raw_query.split()) > _DISTILLATION_WORD_THRESHOLD:
        cache_key = raw_query.strip()
        cached = _distilled_query_cache_get(cache_key)
        if cached is not None:
            result["distilled_query"] = cached[0]
            result["distilled_query_variants"] = cached
        else:
            try:
                registry = get_prompt_registry()
                prompt = registry.get("search_agent/build_search_query").format(
                    problem_statement=raw_query,
                )

                async def _one_distillation() -> str:
                    distilled = (await llm.chat(prompt)).strip()
                    # Light sanitize only — preserve phrase structure for the
                    # embedder; keyword_search_node applies its own stricter,
                    # tsquery-safe pass on top of this.
                    distilled = re.sub(r"[^\w\s\-/]", "", distilled).strip()
                    return distilled

                attempts = await asyncio.gather(
                    *(_one_distillation() for _ in range(_DISTILLATION_VARIANT_ATTEMPTS)),
                    return_exceptions=True,
                )
                variants: list[str] = []
                for attempt in attempts:
                    if isinstance(attempt, BaseException):
                        logger.warning("analyze_query: one of %d distillation attempts failed: %s", _DISTILLATION_VARIANT_ATTEMPTS, attempt)
                        continue
                    if attempt and attempt not in variants:
                        variants.append(attempt)
                if not variants:
                    variants = [raw_query]

                result["distilled_query"] = variants[0]
                result["distilled_query_variants"] = variants
                _distilled_query_cache_set(cache_key, variants)
            except Exception:
                logger.exception("analyze_query distillation failed, falling back to raw query")
                result["distilled_query"] = raw_query
                result["distilled_query_variants"] = [raw_query]

    return result


# ── Node 2: keyword_search_node ────────────────────────────


async def keyword_search_node(
    state: SearchState,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    """Execute full-text keyword search on the user-selected field(s)."""

    filters = _filters_from_dict(state.get("filters", {}))
    search_fields = state.get("search_fields", ["description"])

    # Keyword search wants a small, high-precision AND-list — always cap to
    # the top few terms regardless of whether analyze_query distilled the
    # query, since AND-of-5 terms is meaningfully more likely to hit a real
    # record than AND-of-15-20 (or AND-of-the-full-raw-problem-statement).
    source_text = state.get("distilled_query") or state["query"]
    kw_query = sanitize_for_tsquery(source_text, max_terms=5)

    if not kw_query:
        logger.info("keyword_search_node: no usable terms after sanitization, skipping")
        return {"keyword_results": []}

    all_results = []
    logger.info(f"entered key word search (terms: {kw_query!r})")

    # Search each field separately
    for field in search_fields:
        try:
            field_results = await keyword_search(
                pool=pool,
                query=kw_query,
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

async def semantic_search_node(
    state: SearchState,
    pool: asyncpg.Pool,
    llm: LLMClient,
) -> dict[str, Any]:
    """Generate query embedding then run vector similarity search on selected field(s).

    No score-based relevance cutoff is applied here. A fixed cosine-similarity
    threshold sits too close to real candidates' scores for narrow/sparse
    queries — it was silently dropping genuine mechanism matches before
    relevance_filter_node ever got a chance to judge them (confirmed: a
    query that returned 0 candidates one run surfaced 2 confirmed-relevant
    ones on a later run, purely from score noise around the cutoff). The DB
    query's own `ORDER BY relevance_score DESC LIMIT` already bounds how many
    rows come back per field; relevance_filter_node's top-N cap bounds how
    many actually reach the expensive LLM judgment. A cosine-score floor
    doesn't add precision on top of that — it only risks losing recall.
    """
    filters = _filters_from_dict(state.get("filters", {}))
    search_fields = state.get("search_fields", ["description"])
    all_results = []
    # Search with every distilled variant (see analyze_query /
    # _DISTILLATION_VARIANT_ATTEMPTS), not just the primary one — embedding
    # and searching each, then merging below like the existing per-field
    # union already does. Falls back to the single primary query/raw query
    # when no variants were produced (short queries skip distillation
    # entirely, or a genuinely empty candidate list should just mean no
    # matches, not an error).
    queries = state.get("distilled_query_variants") or [state.get("distilled_query") or state["query"]]
    logger.info(f"entered semantic search with {len(queries)} query variant(s)")

    for query in queries:
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
                    all_results.extend(field_results)
                except Exception as exc:
                    logger.error("semantic_search_node failed for field %s (variant %r): %s", field, query, exc)

        except Exception as exc:
            logger.error("semantic_search_node embedding failed for variant %r: %s", query, exc)

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


# ── Node 5: rerank_candidates ───────────────────────────────

async def rerank_candidates_node(
    state: SearchState,
    llm: LLMClient,
) -> dict[str, Any]:
    """Re-sort candidates by cosine similarity between the query and a
    clean-text embedding of each candidate (description + extracted
    root-cause statement), instead of the stored raw-text embedding score.

    Confirmed empirically: comparing a clean, distilled query against
    candidates' stored embeddings (of their full raw, noisy text) barely
    correlates with genuine failure-mode relevance — a true match ranked
    75th+ out of ~270 candidates. Re-embedding the same clean snippet the
    relevance filter already extracts and comparing against that instead
    pulled true matches from ranks 74-86 up to ranks 1-17 on the same pool.
    """
    final_results = state.get("final_results", [])
    if not final_results:
        return {"final_results": final_results}

    query = state.get("distilled_query") or state.get("query", "")

    try:
        reranked = await rerank_by_clean_embeddings(llm=llm, query=query, candidates=final_results)
        return {"final_results": reranked}
    except Exception:
        logger.exception("rerank_candidates_node failed, falling back to unreranked order")
        return {"final_results": final_results}


# ── Node 6: relevance_filter ───────────────────────────────

async def relevance_filter_node(
    state: SearchState,
    llm: LLMClient,
) -> dict[str, Any]:
    """Drop candidates that are only topically/lexically similar but
    mechanistically unrelated to the current problem statement.

    Cosine similarity alone can't tell these apart — it measures textual
    closeness, not cause identity — so this uses the LLM to judge each
    candidate's own description and documented root cause against the query.
    """
    final_results = state.get("final_results", [])
    if not final_results:
        return {"final_results": final_results}

    # Judge the top-N by relevance_score regardless of the list's current
    # sort order (combine_results_node sorts by date, not score, in pure
    # keyword mode) — the LLM should see the most textually-promising
    # candidates, not an arbitrary date-ordered slice.
    candidates = sorted(
        final_results, key=lambda r: r.get("relevance_score", 0), reverse=True
    )[:_RELEVANCE_FILTER_TOP_N]

    try:
        registry = get_prompt_registry()
        prompt_template = registry.get("search_agent/relevance_filter")
        filtered = await filter_relevant(
            llm=llm,
            prompt_template=prompt_template,
            guard_rail_text=registry.get("guardrail"),
            query=state.get("query", ""),
            candidates=candidates,
        )
        return {"final_results": filtered}
    except Exception:
        logger.exception("relevance_filter_node failed, falling back to unfiltered top-N candidates")
        return {"final_results": candidates}