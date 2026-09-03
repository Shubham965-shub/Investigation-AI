import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from src.agents.capa_depth_effectiveness.api.services.capa_depth_effectiveness_service import call_with_retry
from src.agents.rci_report.api.schemas.measure_analyze import HistoryReviewRow, HistoryReviewSection
from src.agents.search_agent.api.services.filters import resolve_qe_type_filter
from src.agents.search_agent.graph.builder import build_search_graph
from src.config.settings import settings
from src.llm.client import LLMClient

logger = logging.getLogger(__name__)

# The search graph itself returns everything above its relevance threshold —
# truncated here to keep the report's History Review table a reasonable
# length (2026-08-26, per the user: capped from 15 down to 5).
_TOP_K = 5

# Retries for the search-graph invocation itself, not just the cosmetic
# closing narrative below (2026-09-03, per the user: the table was coming
# back empty inconsistently across otherwise-similar records). A transient
# failure anywhere inside the graph — an LLM rate-limit on query
# distillation, an embedding-API blip, a DB pool timeout — was previously
# caught by a bare `except Exception` with zero retry and silently degraded
# straight to "no similar events found," with only a log line. That's not
# what call_with_retry (below, still used for the narrative) covers either —
# it only retries a Pydantic ValidationError from a structured LLM response,
# not a generic transient failure from a whole multi-node graph run.
_SEARCH_MAX_ATTEMPTS = 3
_SEARCH_RETRY_DELAY_SECONDS = 2


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


def _resolve_event_date(event_date_str: Optional[str]) -> datetime:
    """The lookback window's anchor point. Falls back to wall-clock "now"
    only when the caller genuinely has no event date to give (or it fails
    to parse) — previously this was the ONLY behavior, anchoring "24 months"
    to whenever the report happened to be generated rather than to when the
    event itself occurred. For a record whose RCI report is generated weeks
    or months after the event opened (routine in practice), that silently
    shrank the effective lookback and dropped real historical matches that
    fell just outside the drifted window — by an amount that varied per
    record, i.e. inconsistently (2026-09-03, per the user)."""
    if event_date_str:
        try:
            return datetime.fromisoformat(event_date_str)
        except ValueError:
            logger.warning("History review: could not parse event date %r, falling back to now", event_date_str)
    return datetime.utcnow()


async def generate_history_review(
    llm: LLMClient,
    pool: Any,
    *,
    event_type: str,
    search_query: str,
    lookback_months: int,
    narrative_system_prompt: str,
    exclude_id: Optional[str] = None,
    event_date: Optional[str] = None,
) -> HistoryReviewSection:
    """Section 4. Row data is deterministic (a real DB query), never LLM-authored
    — only the one-sentence closing verdict on prior-CAPA effectiveness is
    generated. Reuses search_agent's own graph rather than reimplementing
    search; adds a date_from/date_to filter search_agent's SearchFilters
    already supports end-to-end but no existing call site used.

    exclude_id: the current record's own id. The search query is seeded with
    this record's own description/root-cause text, so without excluding its
    own id it self-matches as a "similar historical event" at near-1.0
    relevance once the record itself is a row in the searchable table.

    event_date: this event's own opened/observed/received date (whichever
    TrackWise field applies for its event type) — anchors the lookback
    window to when the event actually happened, not to "now". Also used as
    date_to's upper bound: history review means events that happened BEFORE
    this one, so an event that occurred after/concurrent with the current
    one was never meant to count as "history" here.
    """
    search_graph = build_search_graph(pool=pool, llm=llm)
    anchor = _resolve_event_date(event_date)
    date_from = (anchor - timedelta(days=30 * lookback_months)).isoformat()
    date_to = anchor.isoformat()
    search_fields = ["description", "root_cause_summary"]
    search_scope_note = (
        f"Semantic search seeded from this event's own description text, run over the "
        f"{'/'.join(search_fields)} fields, scoped to {event_type} events."
    )

    initial_state = {
        "query": search_query,
        "search_fields": search_fields,
        "search_type": "Semantic",
        "filters": {
            "qe_type": resolve_qe_type_filter(event_type),
            "date_from": date_from,
            "date_to": date_to,
            "exclude_id": exclude_id,
        },
        "determined_search_type": "",
        "keyword_results": [],
        "semantic_results": [],
        "final_results": [],
        "ranked_results": [],
        "synthesized_answer": "",
        "source_citations": [],
        "error": None,
    }

    candidates: List[Dict[str, Any]] = []
    for attempt in range(1, _SEARCH_MAX_ATTEMPTS + 1):
        try:
            search_state = await search_graph.ainvoke(initial_state)
            candidates = (search_state.get("final_results") or [])[:_TOP_K]
            break
        except Exception:
            logger.exception("History review search failed on attempt %d/%d", attempt, _SEARCH_MAX_ATTEMPTS)
            if attempt < _SEARCH_MAX_ATTEMPTS:
                await asyncio.sleep(_SEARCH_RETRY_DELAY_SECONDS)

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
