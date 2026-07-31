import logging
from typing import Any
from fastapi import APIRouter, File, HTTPException, UploadFile, status, Form

from src.llm.client import LLMClient
from agents.rot_cause_advisor.api.services.root_cause_advisor_service import (
    generate_root_cause_advice,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rca", tags=["rot_cause_advisor"])


@router.post(
    "/root_cause_advisor",
    summary="Generate structured root cause advisory guidance for a pharma investigation document.",
)
async def root_cause_advisor(
    file: UploadFile = File(...),
    event_type: str = Form(...)
):
    if not event_type or not event_type.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="event_type is required and must be non-empty.",
        )

    llm = LLMClient()

    try:
        advice = await generate_root_cause_advice(
            event_type=event_type.strip(),
            file=file,
            llm=llm,
        )
        return advice

    except HTTPException:
        raise
    except Exception:
        logger.exception("Root cause advisor generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate root cause advisory guidance.",
        )