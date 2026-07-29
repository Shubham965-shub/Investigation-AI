from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from src.clients.ds_client import ds_post
from src.db.field_mapping import build_trackwise_fields, resolved_event_type
from src.db.generated_content_queries import fetch_problem_statement, save_problem_statement
from src.db.module_stage import stage_for
from src.db.queries import fetch_investigation_row
from src.schemas.problem_statement import (
    ProblemStatementGenerateRequest,
    ProblemStatementGenerateResponse,
    ProblemStatementRecord,
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
    )
