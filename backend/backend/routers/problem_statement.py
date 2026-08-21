from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from backend.clients.ds_client import ds_post
from backend.db.field_mapping import build_trackwise_fields, resolved_event_type
from backend.db.generated_content_queries import fetch_evidence_items, fetch_problem_statement, save_problem_statement
from backend.db.module_stage import stage_for
from backend.db.queries import fetch_investigation_row, fetch_investigation_statuses
from backend.schemas.problem_statement import (
    ProblemStatementGenerateRequest,
    ProblemStatementGenerateResponse,
    ProblemStatementRecord,
    SimilarInvestigation,
)

logger = logging.getLogger(__name__)

_NOT_FOUND_DETAIL = "No problem statement found for this investigation yet"

router = APIRouter(prefix="/problem-statement", tags=["Problem Statement"])


@router.post("/{record_id}/generate", response_model=ProblemStatementGenerateResponse)
async def generate_problem_statement(
    record_id: str,
    request: ProblemStatementGenerateRequest,
) -> ProblemStatementGenerateResponse:
    data = await ds_post("/ps/v2/generate", json=request.model_dump())
    response = ProblemStatementGenerateResponse(**data)

    # Persisting is best-effort — a DB/table issue must never break generation
    # itself, especially before generated_content.sql has been run anywhere.
    try:
        deviation_id = int(record_id)
        await save_problem_statement(deviation_id, response.problem_statement)
    except Exception:
        logger.warning("Could not persist problem statement for record_id=%s", record_id, exc_info=True)

    return response


@router.get("/{record_id}", response_model=ProblemStatementRecord)
async def get_problem_statement(record_id: str) -> ProblemStatementRecord:
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    row = await fetch_investigation_row(deviation_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    event_type = resolved_event_type(row["qe_type"])
    if event_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    # Market Complaint gets the extended field set only for problem-statement.
    extended = event_type == "Market Complaint"
    return ProblemStatementRecord(
        record_id=record_id,
        event_type=event_type,
        trackwise_fields=build_trackwise_fields(row, row["qe_type"], extended=extended),
        problem_statement=await fetch_problem_statement(deviation_id),
        stage=stage_for(row["status"]),
        locked_for_editing=bool(await fetch_evidence_items(deviation_id)),
    )


_HISTORIC_RESULTS_LIMIT = 5


@router.get("/{record_id}/historic", response_model=list[SimilarInvestigation])
async def get_similar_historic_investigations(record_id: str) -> list[SimilarInvestigation]:
    """Historic investigations this one is most similar to (open, closed, or
    cancelled), for the "View Historic Data" panel — routed through ds's
    /api/search (contextual/semantic search over its search corpus, joined to
    the full event-details table). Returns [] on any failure (no problem
    statement/description yet to search on, ds unreachable, no candidates)
    rather than raising — this is a supplementary panel, not a hard
    requirement for the Problem Statement page to work.
    """
    try:
        deviation_id = int(record_id)
    except ValueError:
        return []

    row = await fetch_investigation_row(deviation_id)
    if row is None:
        return []

    # Prefer the generated problem statement (more focused/normalized text);
    # fall back to the raw Trackwise description/title if one hasn't been
    # generated yet — same "search_query or ... or 'unknown'" fallback chain
    # ds's own shared/nodes.py::fetch_historical_data already uses internally.
    query_text = await fetch_problem_statement(deviation_id) or row["description"] or row["title"]
    if not query_text:
        return []

    try:
        # search_route.py's router is uniquely prefixed with "/api" (unlike
        # /ps/v2, /evidence, /rci — no other ds route needs it), so the real
        # path is /api/search, not /search.
        data = await ds_post(
            "/api/search",
            json={
                "problem_statement": query_text,
                "search_type": "Contextual",
                # +1 for the current record itself, which ds's search has no
                # way to exclude up front — filtered out below instead.
                "top_k": _HISTORIC_RESULTS_LIMIT + 1,
            },
        )
    except HTTPException:
        logger.warning("Historic-data search failed for record_id=%s", record_id, exc_info=True)
        return []

    candidates = [
        r for r in data.get("ranked_results", [])
        if int(r.get("deviation_id", -1)) != deviation_id
    ][:_HISTORIC_RESULTS_LIMIT]
    if not candidates:
        return []

    status_by_id = await fetch_investigation_statuses([int(c["deviation_id"]) for c in candidates])

    return [
        SimilarInvestigation(
            deviation_id=int(c["deviation_id"]),
            title=c.get("title") or "Untitled",
            status=status_by_id.get(int(c["deviation_id"]), "Unknown"),
            relevance_score=round(float(c.get("relevance_score", 0.0)), 4),
        )
        for c in candidates
    ]
