"""
Shared LangGraph nodes reused by all archetype-mapping workflows.
"""

import asyncpg
import json
import logging
import re
from typing import Any, Optional

from src.config.settings import settings
from src.utils.deps import get_llm_client, get_db_pool, get_prompt_registry

logger = logging.getLogger(__name__)


async def parse_input(state: Any) -> Any:
    """Extract failure_type from the normalised trackwise_fields."""
    trackwise = state.trackwise_fields
    event_type = state.event_type.lower().strip()

    if event_type == "deviation":
        failure_type = trackwise.get("deviation_to") or trackwise.get("description", "Unknown Deviation")
    elif event_type in ["oos", "oot", "oos/oot"]:
        failure_type = trackwise.get("failure_type") or trackwise.get("title", "Unknown OOS/OOT")
    elif event_type == "market complaint":
        failure_type = trackwise.get("title", "Unknown Market Complaint")
    else:
        failure_type = None

    state.failure_type = failure_type
    logger.info(f"Extracted failure_type: {failure_type!r} for event_type: {event_type!r}")
    return state


async def fetch_archetypes(state: Any) -> Any:
    """Fetch archetypes filtered to the workflow's ARCHETYPE_TYPE."""
    archetype_type = type(state).ARCHETYPE_TYPE
    # settings.DATABASE_URL (not a raw f-string) — DB_PASSWORD contains
    # characters (#, ,) that are URL-structural if not percent-encoded;
    # unencoded, asyncpg fails to parse the DSN at all, silently caught by
    # the except below and turning every call into "0 archetypes fetched".
    db_url = settings.DATABASE_URL
    try:
        conn = await asyncpg.connect(db_url)
        try:
            if archetype_type:
                rows = await conn.fetch(
                    """
                    SELECT a.id, a.name, a.definition, a.archetype_type_id
                    FROM archetype a
                    JOIN archetype_type at ON a.archetype_type_id = at.id
                    WHERE at.name = $1
                    ORDER BY a.name
                    """,
                    archetype_type,
                )
            else:
                rows = await conn.fetch(
                    "SELECT id, name, definition, archetype_type_id FROM archetype ORDER BY name"
                )
            state.all_archetypes = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "definition": r["definition"] or "",
                    "archetype_type_id": r["archetype_type_id"],
                }
                for r in rows
            ]
            logger.info(
                f"Fetched {len(state.all_archetypes)} archetypes"
                + (f" (type='{archetype_type}')" if archetype_type else " (all types)")
            )
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Error fetching archetypes: {e}")
        state.all_archetypes = []
    return state


# Matches a "<base name>_Mfg" / "<base name>_Lab" archetype naming convention (the RCI Plan
# library's one deliberate department split today, e.g. "Assay Failure_Mfg"/"Assay Failure_Lab")
# — case-insensitive, trailing whitespace tolerant (the source Excel's own "Assay Failure_Lab "
# sheet tab has a trailing space, stripped at ingestion time).
_DEPARTMENT_SUFFIX_RE = re.compile(r"_(mfg|lab)\s*$", re.IGNORECASE)


def _filter_archetypes_by_department(archetypes: list, investigation_type: Optional[str]) -> list:
    """Deterministically excludes the wrong-department half of a "_Mfg"/"_Lab" archetype pair
    (per the functional team, 2026-09-30: only Assay Failure has this split today, but the rule
    is name-convention-based so it covers any future pair without a code change) — rather than
    leaving that choice to the LLM's fuzzy name/definition match in map_to_archetype below.
    Archetypes with no such suffix (the other ~96 in the library) are untouched. No-op when
    investigation_type is unset (event isn't a dual-RCI OOS/OOT, or dim_rci.is_mfg_rci isn't
    backfilled for it yet) — every candidate stays in play, same as before this existed.
    """
    if not investigation_type:
        return archetypes

    wanted_suffix = "mfg" if investigation_type.strip().lower() == "manufacturing" else "lab"

    by_base: dict = {}
    for a in archetypes:
        match = _DEPARTMENT_SUFFIX_RE.search(a["name"])
        base = _DEPARTMENT_SUFFIX_RE.sub("", a["name"]).strip().lower() if match else None
        by_base.setdefault(base, []).append(a)

    filtered = []
    for base, group in by_base.items():
        if base is None:
            filtered.extend(group)  # no _Mfg/_Lab suffix — not part of a department split
            continue
        by_suffix = {_DEPARTMENT_SUFFIX_RE.search(a["name"]).group(1).lower(): a for a in group}
        if "mfg" in by_suffix and "lab" in by_suffix:
            filtered.append(by_suffix[wanted_suffix])  # genuine pair — keep only the matching half
        else:
            filtered.extend(group)  # only one variant exists for this base name — keep it as-is
    return filtered


async def map_to_archetype(state: Any, rci_id: Optional[str] = None) -> Any:
    """Map the full event context to the closest existing archetype.

    Passes all non-empty trackwise fields to the LLM so it can derive the
    failure mechanism itself rather than relying on a single pre-extracted
    field that may be a document code or otherwise incomplete.

    `rci_id` is accepted but currently unused — groundwork for per-RCI
    archetype matching, to be built out once archetype data differentiates
    by RCI. It is threaded through from `state.rci_id` at each call site so
    it's available without further plumbing when that logic is added.
    """
    try:
        llm = await get_llm_client()
    except Exception:
        from src.llm.client import LLMClient
        llm = LLMClient()

    registry = get_prompt_registry()
    candidates = _filter_archetypes_by_department(
        state.all_archetypes, state.trackwise_fields.get("investigation_type")
    )
    archetype_list = "\n".join(
        f"- {a['name']}: {a['definition']}" if a.get("definition") else f"- {a['name']}"
        for a in candidates
    )
    tw_fields_str = "\n".join(
        f"  {k}: {v}" for k, v in state.trackwise_fields.items() if v
    )
    prompt = registry.get("shared/map_to_archetype").format(
        event_type=state.event_type,
        tw_fields_str=tw_fields_str,
        archetype_list=archetype_list,
    )

    result = await llm.chat(prompt)

    try:
        mapping = json.loads(result.strip())
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON from LLM in map_to_archetype: {result}")
        mapping = {
            "archetype_name": state.all_archetypes[0]["name"] if state.all_archetypes else (state.failure_type or ""),
            "confidence_score": 0.1,
            "reasoning": "Fallback due to JSON parsing error",
        }

    matched_name = mapping.get("archetype_name", "")
    state.mapped_archetype = next(
        (a for a in state.all_archetypes if a["name"].lower() == matched_name.lower()),
        None,
    )
    if state.mapped_archetype is None and matched_name:
        state.mapped_archetype = {"id": None, "name": matched_name, "archetype_type_id": None}

    state.is_new_archetype = False
    state.confidence_score = float(mapping.get("confidence_score", 0.0))
    state.reasoning = mapping.get("reasoning", "")

    logger.info(
        f"Mapped to archetype: {matched_name!r} "
        f"(confidence={state.confidence_score:.2f}) — {state.reasoning}"
    )
    return state



async def build_search_query(state: Any) -> Any:
    """Build a structured semantic search phrase from trackwise fields.

    Uses an event-type-aware prompt to extract the most discriminating
    technical anchors (test name, instrument, failure mode, etc.) rather
    than generic keywords, producing a phrase optimised for vector similarity.
    """
    llm = await get_llm_client()
    registry = get_prompt_registry()

    # Pass ALL trackwise fields so the LLM can find priority fields by name
    tw_text = "\n".join(f"- {k}: {v}" for k, v in state.trackwise_fields.items() if v)

    prompt = registry.get("shared/build_search_query").format(
        event_type=state.event_type,
        tw_text=tw_text,
    )
    try:
        result = await llm.chat(prompt)
        query = result.strip()
        # Light sanitisation — preserve phrase structure, just strip dangerous chars
        query = re.sub(r"[^\w\s\-/]", "", query).strip()
        state.search_query = query or state.failure_type or "unknown"
    except Exception:
        logger.exception("LLM query builder failed, falling back to failure_type")
        state.search_query = re.sub(r"[^\w\s\-]", "", state.failure_type or "unknown").strip()

    logger.info(f"Built semantic search query: {state.search_query!r}")
    return state


_HISTORICAL_TOP_K = 15  # Maximum candidates passed to the inference step.
                        # The search graph returns all results above its
                        # relevance threshold; we take the top-K by score
                        # here rather than in the shared search graph so the
                        # main search feature is unaffected.


async def fetch_historical_data(state: Any) -> Any:
    """Search historical incidents using the pre-built problem statement query.

    Uses Semantic-only search so that a mechanism-level description embeds
    into a precise vector, avoiding the broad keyword over-matching that
    previously returned 100+ loosely related records.

    Results are truncated to _HISTORICAL_TOP_K (already sorted by cosine
    score descending by combine_results_node) before being stored in state.
    """
    from src.agents.search_agent.api.services.filters import resolve_qe_type_filter
    from src.agents.search_agent.graph.builder import build_search_graph

    pool = await get_db_pool()
    llm = await get_llm_client()
    search_graph = build_search_graph(pool=pool, llm=llm)
    query = state.search_query or state.failure_type or "unknown"

    initial_state = {
        "query": query,
        "search_fields": ["description", "root_cause_summary"],
        "search_type": "Semantic",
        "filters": {"qe_type": resolve_qe_type_filter(state.event_type)},
        "determined_search_type": "",
        "keyword_results": [],
        "semantic_results": [],
        "final_results": [],
        "ranked_results": [],
        "synthesized_answer": "",
        "source_citations": [],
        "error": None,
    }

    try:
        search_state = await search_graph.ainvoke(initial_state)
        all_results = search_state.get("final_results", []) or []
    except Exception:
        logger.exception("Historical search graph failed")
        all_results = []

    # Truncate here — search graph returns everything above its threshold,
    # sorted descending by relevance score. Take only the top candidates.
    state.search_results = all_results[:_HISTORICAL_TOP_K]
    for r in state.search_results:
        title = r.get("title", "Untitled")
        print(f"- {title} (score: {r.get('relevance_score', 0):.2f})")

    logger.info(
        f"Historical search: {len(all_results)} results above threshold, "
        f"using top {len(state.search_results)} (query: {query!r})"
    )
    return state

