from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from src.clients.ds_client import ds_post
from src.db.field_mapping import build_trackwise_fields, resolved_event_type
from src.db.generated_content_queries import fetch_questionnaire_items, replace_questionnaire_items
from src.db.module_stage import stage_for
from src.db.queries import fetch_investigation_row
from src.schemas.questionnaire import (
    InterviewQuestion,
    QuestionnaireGenerateRequest,
    QuestionnaireGenerateResponse,
    QuestionnaireRecord,
)

logger = logging.getLogger(__name__)

_NOT_FOUND_DETAIL = "No questionnaire found for this investigation yet"

router = APIRouter(prefix="/questionnaire", tags=["Interview Questionnaire"])


@router.post("/{record_id}/generate", response_model=QuestionnaireGenerateResponse)
async def generate_questionnaire(
    record_id: str,
    request: QuestionnaireGenerateRequest,
) -> QuestionnaireGenerateResponse:
    data = await ds_post("/interview/questionnaire", json=request.model_dump())
    response = QuestionnaireGenerateResponse(**data)

    # Persisting is best-effort — a DB/table issue must never break generation
    # itself, especially before generated_content.sql has been run anywhere.
    try:
        deviation_id = int(record_id)
        await replace_questionnaire_items(
            deviation_id,
            [{"description": q.description, "is_checked": True} for q in response.questions],
        )
    except Exception:
        logger.warning("Could not persist questionnaire items for record_id=%s", record_id, exc_info=True)

    return response


@router.get("/{record_id}", response_model=QuestionnaireRecord)
async def get_questionnaire(record_id: str) -> QuestionnaireRecord:
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

    persisted = await fetch_questionnaire_items(deviation_id)
    return QuestionnaireRecord(
        record_id=record_id,
        event_type=event_type,
        trackwise_fields=build_trackwise_fields(row, row["qe_type"], extended=False),
        questions=[InterviewQuestion(**item) for item in persisted] if persisted else None,
        stage=stage_for(row["status"]),
    )
