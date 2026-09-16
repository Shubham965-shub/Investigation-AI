from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from backend.clients.ds_client import ds_post
from backend.db.field_mapping import build_trackwise_fields, resolved_event_type
from backend.db.generated_content_queries import fetch_evidence_items, replace_evidence_items
from backend.db.module_stage import stage_for
from backend.db.queries import fetch_investigation_row
from backend.schemas.evidence import (
    EvidenceCollectionRecord,
    EvidenceCollectionRequest,
    EvidenceCollectionResponse,
    EvidenceItem,
)

logger = logging.getLogger(__name__)

_NOT_FOUND_DETAIL = "No evidence list found for this investigation yet"

router = APIRouter(prefix="/evidence", tags=["Evidence Collection"])


@router.post("/{record_id}/collect", response_model=EvidenceCollectionResponse)
async def collect_evidence(record_id: str, request: EvidenceCollectionRequest) -> EvidenceCollectionResponse:
    data = await ds_post("/evidence/collect", json=request.model_dump())
    response = EvidenceCollectionResponse(**data)

    # Persisting is best-effort; a DB issue must not break generation itself.
    try:
        deviation_id = int(record_id)
        await replace_evidence_items(
            deviation_id,
            [{"description": item.description, "is_checked": True} for item in response.evidence],
        )
    except Exception:
        logger.warning("Could not persist evidence items for record_id=%s", record_id, exc_info=True)

    return response


@router.get("/{record_id}", response_model=EvidenceCollectionRecord)
async def get_evidence(record_id: str) -> EvidenceCollectionRecord:
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

    persisted = await fetch_evidence_items(deviation_id)
    return EvidenceCollectionRecord(
        record_id=record_id,
        event_type=event_type,
        trackwise_fields=build_trackwise_fields(row, row["qe_type"], extended=False),
        evidence=[EvidenceItem(**item) for item in persisted] if persisted else None,
        stage=stage_for(row["status"]),
    )


@router.put("/{record_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def update_evidence(record_id: str, items: list[EvidenceItem]) -> None:
    """Full replace of persisted evidence state, triggered by user edits instead of generation."""
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    await replace_evidence_items(
        deviation_id,
        [{"description": item.description, "is_checked": item.is_checked} for item in items],
    )
