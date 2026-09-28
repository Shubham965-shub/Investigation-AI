from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from backend.clients.ds_client import ds_post
from backend.db.field_mapping import build_trackwise_fields, normalize_rci_id, resolved_event_type
from backend.db.generated_content_queries import (
    delete_problem_statement_enhancements,
    fetch_evidence_items,
    fetch_problem_statement,
    fetch_problem_statement_enhancements,
    save_problem_statement,
    save_problem_statement_enhancements,
)
from backend.db.module_stage import stage_for
from backend.db.queries import fetch_investigation_row, fetch_investigation_statuses
from backend.routers.auth import get_current_payload
from backend.schemas.problem_statement import (
    ProblemStatementEnhancementsResponse,
    ProblemStatementGenerateRequest,
    ProblemStatementGenerateResponse,
    ProblemStatementRecord,
    ProblemStatementUpdateRequest,
    SimilarInvestigation,
)

logger = logging.getLogger(__name__)

_NOT_FOUND_DETAIL = "No problem statement found for this investigation yet"

router = APIRouter(prefix="/problem-statement", tags=["Problem Statement"])


@router.post("/{record_id}/{rci_id}/generate", response_model=ProblemStatementGenerateResponse)
async def generate_problem_statement(
    record_id: str,
    rci_id: str,
    request: ProblemStatementGenerateRequest,
    claims: dict = Depends(get_current_payload),
) -> ProblemStatementGenerateResponse:
    resolved_rci_id = normalize_rci_id(rci_id)
    data = await ds_post("/ps/v2/generate", json=request.model_dump())
    response = ProblemStatementGenerateResponse(**data)

    # Persisting is best-effort; a DB issue must not break generation itself.
    try:
        deviation_id = int(record_id)
        await save_problem_statement(
            deviation_id, response.problem_statement, rci_id=resolved_rci_id, generated_by=claims.get("uid")
        )
    except Exception:
        logger.warning("Could not persist problem statement for record_id=%s", record_id, exc_info=True)

    return response


@router.get("/{record_id}/{rci_id}", response_model=ProblemStatementRecord)
async def get_problem_statement(record_id: str, rci_id: str) -> ProblemStatementRecord:
    resolved_rci_id = normalize_rci_id(rci_id)
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    row = await fetch_investigation_row(deviation_id, rci_id=resolved_rci_id)
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
        problem_statement=await fetch_problem_statement(deviation_id, rci_id=resolved_rci_id),
        stage=stage_for(row["status"]),
        locked_for_editing=bool(await fetch_evidence_items(deviation_id, rci_id=resolved_rci_id)),
        criticality=row["criticality"],
        event_classification=row["event_classification"],
        enhancements=await fetch_problem_statement_enhancements(deviation_id, rci_id=resolved_rci_id),
    )


@router.post("/{record_id}/{rci_id}/enhancements/generate", response_model=ProblemStatementEnhancementsResponse)
async def generate_problem_statement_enhancements(record_id: str, rci_id: str) -> ProblemStatementEnhancementsResponse:
    """Categorized diff between the raw TrackWise description and the already-generated problem
    statement, for the "What Was Enhanced" panel. Reads both from what's already persisted —
    no request body needed."""
    resolved_rci_id = normalize_rci_id(rci_id)
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    problem_statement = await fetch_problem_statement(deviation_id, rci_id=resolved_rci_id)
    if not problem_statement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    row = await fetch_investigation_row(deviation_id, rci_id=resolved_rci_id)
    raw_description = (row["description"] if row else None) or ""

    data = await ds_post(
        "/ps/v2/enhancements",
        json={"raw_description": raw_description, "problem_statement": problem_statement},
    )
    response = ProblemStatementEnhancementsResponse(**data)

    try:
        await save_problem_statement_enhancements(
            deviation_id, [item.model_dump() for item in response.enhancements], rci_id=resolved_rci_id
        )
    except Exception:
        logger.warning("Could not persist problem statement enhancements for record_id=%s", record_id, exc_info=True)

    return response


@router.put("/{record_id}/{rci_id}", response_model=ProblemStatementRecord)
async def update_problem_statement(
    record_id: str, rci_id: str, request: ProblemStatementUpdateRequest, claims: dict = Depends(get_current_payload)
) -> ProblemStatementRecord:
    """Persists a manual edit to an already-generated problem statement; locked once Evidence Collection has data, same as GET's locked_for_editing rule."""
    resolved_rci_id = normalize_rci_id(rci_id)
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    row = await fetch_investigation_row(deviation_id, rci_id=resolved_rci_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    event_type = resolved_event_type(row["qe_type"])
    if event_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    if await fetch_evidence_items(deviation_id, rci_id=resolved_rci_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Evidence Collection has already started — the problem statement can no longer be edited.",
        )

    await save_problem_statement(
        deviation_id, request.problem_statement, rci_id=resolved_rci_id, generated_by=claims.get("uid")
    )
    try:
        await delete_problem_statement_enhancements(deviation_id, rci_id=resolved_rci_id)
    except Exception:
        logger.warning("Could not clear stale problem statement enhancements for record_id=%s", record_id, exc_info=True)

    extended = event_type == "Market Complaint"
    return ProblemStatementRecord(
        record_id=record_id,
        event_type=event_type,
        trackwise_fields=build_trackwise_fields(row, row["qe_type"], extended=extended),
        problem_statement=request.problem_statement,
        stage=stage_for(row["status"]),
        locked_for_editing=False,
        criticality=row["criticality"],
        event_classification=row["event_classification"],
    )


_HISTORIC_RESULTS_LIMIT = 5


@router.get("/{record_id}/{rci_id}/historic", response_model=list[SimilarInvestigation])
async def get_similar_historic_investigations(record_id: str, rci_id: str) -> list[SimilarInvestigation]:
    """Similar historic investigations for the "View Historic Data" panel; returns [] on any failure since this is a supplementary panel, not a hard requirement."""
    resolved_rci_id = normalize_rci_id(rci_id)
    try:
        deviation_id = int(record_id)
    except ValueError:
        return []

    row = await fetch_investigation_row(deviation_id, rci_id=resolved_rci_id)
    if row is None:
        return []

    # Fall back to raw Trackwise description/title if no problem statement has been generated yet.
    query_text = await fetch_problem_statement(deviation_id, rci_id=resolved_rci_id) or row["description"] or row["title"]
    if not query_text:
        return []

    try:
        data = await ds_post(
            "/api/search",  # unlike /ps/v2, /evidence, /rci, this ds route is prefixed with /api
            json={
                "problem_statement": query_text,
                "search_type": "Contextual",
                "top_k": _HISTORIC_RESULTS_LIMIT + 1,  # +1 for the current record, filtered out below
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
