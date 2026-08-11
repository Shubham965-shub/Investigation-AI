"""Search endpoint — the public-facing API for the agentic search agent."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from src.utils.deps import get_db_pool, get_llm_client
from src.agents.search_agent.api.schemas import (
    SearchRequest,
    SearchResponse,
    SearchTypeOption,
    SearchViaOption,
    SearchResultItem,
    LlmData,
    CumulativeSummaryRequest,
    CumulativeSummaryItem,
)
from src.agents.search_agent.graph.builder import build_search_graph
from src.agents.search_agent.graph.state import SearchState
from src.config.settings import settings
from src.agents.search_agent.api.services.filters import parse_date_range, SearchFilters
import asyncpg
from src.agents.search_agent.api.services.executive_service import (
    _get_executive_narrative,
    _get_top_cause_description,
    _get_capa_recurring_themes,
    get_final_ranked_results,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["search"])


# ── Cumulative Summary Endpoint ────────────────────────────────

@router.post("/cummulative_summary", response_model=list[CumulativeSummaryItem])
async def cummulative_summary(
    body: CumulativeSummaryRequest,
    pool=Depends(get_db_pool),
) -> list[CumulativeSummaryItem]:
    """
    Return a cumulative summary of the provided deviation IDs.

    Column mapping (configured via .env):
      - event_description   <- SUMMARY_COL_EVENT_DESCRIPTION   (default: title)
      - root_cause          <- SUMMARY_COL_ROOT_CAUSE           (default: root_cause_summary_summary)
      - capa                <- SUMMARY_COL_CAPA                 (default: capa_details_summary)
      - implementation_date <- SUMMARY_COL_IMPLEMENTATION_DATE  (default: Capa_Date)
    """
    summary_table = settings.SUMMARY_TABLE
    search_table = settings.COLUMN_CAPA_IMPLEMENTATION_DATE
    id_column = settings.SUMMARY_ID_COLUMN

    if not body.deviation_id:
        return []

    async with pool.acquire() as db_conn:
        try:
            query = f'SELECT * FROM "{summary_table}" WHERE "{id_column}" = ANY($1)'
            rows = await db_conn.fetch(query, body.deviation_id)
        except asyncpg.exceptions.DatatypeMismatchError:
            text_ids = [str(x) for x in body.deviation_id]
            query = f'SELECT * FROM "{summary_table}" WHERE "{id_column}" = ANY($1::text[])'
            rows = await db_conn.fetch(query, text_ids)
        except Exception as e:
            text_ids = [str(x) for x in body.deviation_id]
            try:
                query = f'SELECT * FROM "{summary_table}" WHERE "{id_column}" = ANY($1::text[])'
                rows = await db_conn.fetch(query, text_ids)
            except Exception:
                raise e

    results = []
    for row in rows:
        row_dict = dict(row)

        # asyncpg returns column names in lowercase regardless of how they were
        # defined in the DB. Build a case-insensitive lookup so that settings
        # values like "Capa_Date" still resolve correctly.
        row_lower = {k.lower(): v for k, v in row_dict.items()}

        def ci_get(col_name: str):
            """Return the value for col_name using a case-insensitive key lookup."""
            return row_lower.get(col_name.lower())

        # ── deviation_id ─────────────────────────────────────────
        deviation_id = str(ci_get(id_column) or "")

        # ── event_description  <-  title column ──────────────────
        event_description = ci_get(settings.SUMMARY_COL_EVENT_DESCRIPTION)

        # ── root_cause  <-  root_cause_summary_summary column ────
        root_cause = ci_get(settings.SUMMARY_COL_ROOT_CAUSE)

        # ── capa  <-  capa_details_summary column ────────────────
        # 1. Strip all newline / carriage-return characters from the raw value.
        # 2. Split on "-" (the delimiter between CAPA points).
        # 3. Strip whitespace from each segment and drop empty ones.
        # 4. If the DB value is null/empty, fall back to ["N/A"].
        capa_raw = ci_get(settings.SUMMARY_COL_CAPA)
        if capa_raw:
            cleaned = str(capa_raw).replace("\r\n", "").replace("\n", "").replace("\r", "")
            parts = [part.strip() for part in cleaned.split("-") if part.strip()]
            capa = parts if parts else ["N/A"]
        else:
            capa = ["N/A"]

       # ── implementation_date  <-  capa_date column ──
        impl_date_raw = ci_get("capa_date")
        logger.info(f"implementation data (raw): {impl_date_raw}")

        implementation_date = (
            str(impl_date_raw) if impl_date_raw is not None else None
        )


        results.append(
            CumulativeSummaryItem(
                deviation_id=deviation_id,
                event_description=event_description,
                root_cause=root_cause,
                capa=capa,
                implementation_date=implementation_date,
            )
        )

    return results


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    pool=Depends(get_db_pool),
    llm=Depends(get_llm_client),
) -> SearchResponse:
    """
    Execute the agentic search workflow:

    1. Analyse the query (GPT-4o) → determine search type + filters
    2. Run keyword and/or semantic search against pgvector
    3. Rerank results (GPT-4o)
    4. Synthesise a natural-language answer with citations (GPT-4o)
    """
    start = time.perf_counter()
    
    # DEBUG: Log incoming request
    logger.info(f"[SEARCH REQUEST] problem_statement={body.problem_statement}, search_type={body.search_type}, sfg_code={body.product_code}, search_on={body.search_on}")

    # Import here to avoid circular dependencies


    # Map search_via to search_fields
    if body.search_via == SearchViaOption.ROOT_CAUSE:
        search_fields = ["root_cause_summary"]
    elif body.search_via == SearchViaOption.EVENT_DESCRIPTION:
        search_fields = ["description"]
    else:  # Both
        search_fields = ["description", "root_cause_summary"]

    # Parse date range to absolute dates
    date_from, date_to = parse_date_range(
        body.date_range.value,
        body.custom_date_from,
        body.custom_date_to,
    )

    # Build filters from new parameters
    filters = SearchFilters(
        qe_type=body.search_on,
        date_from=date_from,
        date_to=date_to,
        locations=body.sites if not any(s.lower() == "all" for s in body.sites) else None,
        instruments=body.instruments if not any(i.lower() == "all" for i in body.instruments) else None,
        materials=body.materials if not any(m.lower() == "all" for m in body.materials) else None,
        sfg_code=body.product_code if not any(m.lower() == "all" for m in body.product_code) else None,
    )

    # Map search_type to internal format
    search_type_map = {
        SearchTypeOption.KEYWORD: "keyword",
        SearchTypeOption.CONTEXTUAL: "semantic",
        SearchTypeOption.HYBRID: "auto",
    }
    internal_search_type = search_type_map[body.search_type]

    # Prepare initial graph state
    initial_state: SearchState = {
        "query": body.problem_statement,
        "search_fields": search_fields,
        "search_type": internal_search_type,
        "filters": {
            "qe_type": filters.qe_type,
            "date_from": filters.date_from.isoformat() if filters.date_from else None,
            "date_to": filters.date_to.isoformat() if filters.date_to else None,
            "locations": filters.locations,
            "instruments": filters.instruments,
            "materials": filters.materials,
            "sfg_code": filters.sfg_code
        },
#        "query_analysis": {},
        "determined_search_type": "",
        "keyword_results": [],
        "semantic_results": [],
        "final_results": [],
        "ranked_results": [],
        "synthesized_answer": "",
        "source_citations": [],
        "error": None,
    }

    # Build and run the graph
    graph = build_search_graph(pool=pool, llm=llm)

    try:
        final_state: SearchState = await graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("Graph execution failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    elapsed = round(time.perf_counter() - start, 3)

    # Assemble response

    # Always prefer final ranked results if available
    ranked = get_final_ranked_results(state=final_state)

    # Construct dynamic llmData by awaiting temporary functions
    # Pass `final_state` to these functions so that later on, they can use the actual search results to generate dynamic content.
    executive_narrative = await _get_executive_narrative(final_state, body = body)
    top_cause_desc = await _get_top_cause_description(final_state, body = body)
    capa_themes = await _get_capa_recurring_themes(final_state)

    llm_data = LlmData(
    executiveNarrative=executive_narrative,
    topCauseDescription=top_cause_desc,
    correctiveActionSummary=(
        "The reported corrective actions predominantly involved immediate technical "
        "interventions addressing machine-related deviations, including tightening of "
        "connections, replacement of affected components, and system verification to "
        "restore analytical sequences without product impact."
    ),
    preventiveActionSummary=(
        "Preventive actions primarily focused on avoiding recurrence of machine-related "
        "issues through reinforcement of preventive maintenance practices, enhanced "
        "monitoring of equipment connections, and adherence to established verification "
        "procedures across analytical operations."
    ),
    capaRecurringThemes=capa_themes,
)



    return SearchResponse(
        ranked_results=[
            SearchResultItem(**r)  # Pass all fields directly since schema allows extra fields
            for r in ranked
        ],
#        synthesized_answer=final_state.get("synthesized_answer", ""),
        # source_citations=[
        #     SourceCitation(**c) for c in final_state.get("source_citations", [])
        # ],
        search_metadata={
            "search_fields": search_fields,
            "search_via": body.search_via.value,
            "search_type_requested": body.search_type.value,
            "search_type_used": final_state.get("determined_search_type", "unknown"),
            "filters_applied": {
                "search_on": body.search_on,
                "date_range": body.date_range.value,
                "sites": body.sites,
                "instruments": body.instruments,
                "materials": body.materials,
                "sfg_code": body.product_code
            },
            "total_candidates": len(final_state.get("final_results", [])),
            "elapsed_seconds": elapsed,
        },
        llmData=llm_data,
    )
