from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from backend.clients.ds_client import ds_post
from backend.db.field_mapping import build_trackwise_fields, normalize_rci_id, resolved_event_type
from backend.db.generated_content_queries import fetch_questionnaire_items, replace_questionnaire_items
from backend.db.module_stage import stage_for
from backend.db.queries import fetch_investigation_row
from backend.routers.auth import get_current_payload
from backend.schemas.questionnaire import (
    InterviewQuestion,
    QuestionnaireGenerateRequest,
    QuestionnaireGenerateResponse,
    QuestionnaireRecord,
)

logger = logging.getLogger(__name__)

_NOT_FOUND_DETAIL = "No questionnaire found for this investigation yet"

router = APIRouter(prefix="/questionnaire", tags=["Interview Questionnaire"])


@router.post("/{record_id}/{rci_id}/generate", response_model=QuestionnaireGenerateResponse)
async def generate_questionnaire(
    record_id: str,
    rci_id: str,
    request: QuestionnaireGenerateRequest,
    claims: dict = Depends(get_current_payload),
) -> QuestionnaireGenerateResponse:
    resolved_rci_id = normalize_rci_id(rci_id)
    data = await ds_post("/interview/questionnaire", json=request.model_dump())
    response = QuestionnaireGenerateResponse(**data)

    # Persisting is best-effort; a DB issue must not break generation itself.
    try:
        deviation_id = int(record_id)
        await replace_questionnaire_items(
            deviation_id,
            [{"description": q.description, "is_checked": True} for q in response.questions],
            rci_id=resolved_rci_id,
            generated_by=claims.get("uid"),
        )
    except Exception:
        logger.warning("Could not persist questionnaire items for record_id=%s", record_id, exc_info=True)

    return response


@router.get("/{record_id}/{rci_id}", response_model=QuestionnaireRecord)
async def get_questionnaire(record_id: str, rci_id: str) -> QuestionnaireRecord:
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

    persisted = await fetch_questionnaire_items(deviation_id, rci_id=resolved_rci_id)
    return QuestionnaireRecord(
        record_id=record_id,
        event_type=event_type,
        trackwise_fields=build_trackwise_fields(row, row["qe_type"], extended=False),
        questions=[InterviewQuestion(**item) for item in persisted] if persisted else None,
        stage=stage_for(row["status"]),
    )


@router.put("/{record_id}/{rci_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def update_questionnaire(
    record_id: str, rci_id: str, items: list[InterviewQuestion], claims: dict = Depends(get_current_payload)
) -> None:
    """Full replace of persisted questionnaire state, triggered by user edits instead of generation."""
    resolved_rci_id = normalize_rci_id(rci_id)
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    await replace_questionnaire_items(
        deviation_id,
        [{"description": item.description, "is_checked": item.is_checked} for item in items],
        rci_id=resolved_rci_id,
        generated_by=claims.get("uid"),
    )
