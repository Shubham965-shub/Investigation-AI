import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from src.agents.capa_depth_effectiveness.api.services.capa_depth_effectiveness_service import call_with_retry
from src.agents.rci_report.api.schemas.measure_analyze import HistoryReviewRow, HistoryReviewSection
from src.agents.search_agent.graph.builder import build_search_graph
from src.config.settings import settings
from src.llm.client import LLMClient

logger = logging.getLogger(__name__)

# The search graph itself returns everything above its relevance threshold —
# truncated here to keep the report's History Review table a reasonable
# length (2026-08-26, per the user: capped from 15 down to 5).
_TOP_K = 5


class HistoryReviewNarrative(BaseModel):
    closing_narrative: str


async def _hydrate_capa_columns(pool: Any, deviation_ids: List[Any]) -> Dict[str, Dict[str, str]]:
    """CAPA description/implementation date live only in the summary table
    (t_deviations_summary), not the search table (t_deviations_vector) —
    same LEFT JOIN this endpoint already does in
    search_agent/api/routes/event_synthesizer_route.py, reused here rather
    than reimplemented.
    """
    if not deviation_ids or not settings.SUMMARY_TABLE:
        return {}

    query = f"""
        SELECT
            "{settings.SUMMARY_ID_COLUMN}"::text AS deviation_id,
            "{settings.SUMMARY_COL_CAPA}" AS capa_description,
            "{settings.SUMMARY_COL_CAPA_DATE}" AS capa_implementation_date
        FROM "{settings.SUMMARY_TABLE}"
        WHERE "{settings.SUMMARY_ID_COLUMN}"::text = ANY($1::text[])
    """
    ids_as_text = [str(d) for d in deviation_ids]
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, ids_as_text)
    except Exception:
        logger.exception("CAPA summary-table hydration failed — history rows will have blank CAPA columns")
        return {}

    return {
        row["deviation_id"]: {
            "capa_description": row["capa_description"] or "",
            "capa_implementation_date": (
                str(row["capa_implementation_date"]) if row["capa_implementation_date"] else ""
            ),
        }
        for row in rows
    }


def _rows_from_search_results(
    candidates: List[Dict[str, Any]], capa_by_id: Dict[str, Dict[str, str]]
) -> List[HistoryReviewRow]:
    rows: List[HistoryReviewRow] = []
    for candidate in candidates:
        deviation_id = str(candidate.get(settings.COLUMN_ID) or candidate.get("deviation_id") or "")
        capa = capa_by_id.get(deviation_id, {})
        rows.append(
            HistoryReviewRow(
                event_number=deviation_id,
                event_title=str(candidate.get("title") or candidate.get(settings.COLUMN_DESCRIPTION) or ""),
                capa_description=capa.get("capa_description", ""),
                capa_implementation_date=capa.get("capa_implementation_date", ""),
            )
        )
    return rows


async def generate_history_review(
    llm: LLMClient,
    pool: Any,
    *,
    event_type: str,
    search_query: str,
    lookback_months: int,
    narrative_system_prompt: str,
    exclude_id: Optional[str] = None,
) -> HistoryReviewSection:
    """Section 4. Row data is deterministic (a real DB query), never LLM-authored
    — only the one-sentence closing verdict on prior-CAPA effectiveness is
    generated. Reuses search_agent's own graph rather than reimplementing
    search; adds a date_from filter search_agent's SearchFilters already
    supports end-to-end but no existing call site uses.

    exclude_id: the current record's own id. The search query is seeded with
    this record's own description/root-cause text, so without excluding its
    own id it self-matches as a "similar historical event" at near-1.0
    relevance once the record itself is a row in the searchable table.
    """
    search_graph = build_search_graph(pool=pool, llm=llm)
    date_from = (datetime.utcnow() - timedelta(days=30 * lookback_months)).isoformat()
    search_fields = ["description", "root_cause_summary"]
    search_scope_note = (
        f"Semantic search seeded from this event's own description text, run over the "
        f"{'/'.join(search_fields)} fields, scoped to {event_type} events."
    )

    initial_state = {
        "query": search_query,
        "search_fields": search_fields,
        "search_type": "Semantic",
        "filters": {"qe_type": event_type, "date_from": date_from, "exclude_id": exclude_id},
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
        candidates = (search_state.get("final_results") or [])[:_TOP_K]
    except Exception:
        logger.exception("History review search failed")
        candidates = []

    deviation_ids = [c.get(settings.COLUMN_ID) or c.get("deviation_id") for c in candidates]
    deviation_ids = [d for d in deviation_ids if d is not None]
    capa_by_id = await _hydrate_capa_columns(pool, deviation_ids)
    rows = _rows_from_search_results(candidates, capa_by_id)

    if rows:
        rows_text = "\n".join(
            f"- Event {r.event_number} ({r.event_title}): CAPA={r.capa_description or 'none recorded'}, "
            f"implemented={r.capa_implementation_date or 'unknown'}"
            for r in rows
        )
    else:
        rows_text = "(no similar historical events found in the lookback window)"

    narrative_user_prompt = (
        f"Event type: {event_type}\nLookback window: {lookback_months} months\n\n"
        f"Historical events found:\n{rows_text}\n\n"
        "Write a single closing sentence on whether the same/similar root cause "
        "has recurred and whether prior CAPAs were effective."
    )
    narrative = await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=narrative_system_prompt,
            user_prompt=narrative_user_prompt,
            structure=HistoryReviewNarrative,
        ),
        label="history_review_narrative",
    )

    return HistoryReviewSection(
        lookback_months=lookback_months,
        search_scope_note=search_scope_note,
        rows=rows,
        no_similar_events_found=not rows,
        closing_narrative=narrative.closing_narrative,
    )
