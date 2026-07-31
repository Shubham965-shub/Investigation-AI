from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from backend.clients.ds_client import ds_post, get_client
from backend.db.field_mapping import build_trackwise_fields, resolved_event_type
from backend.db.generated_content_queries import fetch_rci_sections, replace_rci_sections
from backend.db.module_stage import stage_for
from backend.db.queries import fetch_investigation_row
from backend.schemas.rci_plan import (
    RciPlanGenerateRequest,
    RciPlanGenerateResponse,
    RciPlanRecord,
    RciSectionItem,
    RciTemplateUploadResponse,
)
from backend.services.rci_plan_export import build_rci_plan_docx

logger = logging.getLogger(__name__)

_NOT_FOUND_DETAIL = "No RCI plan found for this investigation yet"

router = APIRouter(prefix="/rci-plan", tags=["RCI Plan"])


@router.post("/{record_id}/generate", response_model=RciPlanGenerateResponse)
async def generate_rci_plan(record_id: str, request: RciPlanGenerateRequest) -> RciPlanGenerateResponse:
    data = await ds_post("/rci/plan", json=request.model_dump())
    response = RciPlanGenerateResponse(**data)

    # Persisting is best-effort — a DB/table issue must never break generation
    # itself, especially before generated_content.sql has been run anywhere.
    try:
        deviation_id = int(record_id)
        await replace_rci_sections(
            deviation_id,
            [
                {
                    "title": section.title,
                    "correlation": section.correlation,
                    "due_date": None,
                    "assignee": None,
                    "tasks": [{"description": task.description, "is_checked": task.is_checked} for task in section.tasks],
                }
                for section in response.sections
            ],
        )
    except Exception:
        logger.warning("Could not persist RCI plan sections for record_id=%s", record_id, exc_info=True)

    return response


@router.post("/upload", response_model=RciTemplateUploadResponse)
async def upload_rci_templates(file: UploadFile = File(...)) -> RciTemplateUploadResponse:
    client = get_client()
    contents = await file.read()
    try:
        response = await client.post(
            "/rci/upload",
            files={"file": (file.filename, contents, file.content_type)},
        )
        response.raise_for_status()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"InvestigationAi_DS service unreachable: {exc}",
        ) from exc
    return RciTemplateUploadResponse(**response.json())


@router.put("/{record_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def update_rci_plan(record_id: str, sections: list[RciSectionItem]) -> None:
    """Full replace of the persisted sections — used to save investigator-name
    edits made directly on the RCI Plan page (see RciPlanPage.tsx)."""
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    await replace_rci_sections(
        deviation_id,
        [
            {
                "title": section.title,
                "correlation": section.correlation,
                "due_date": section.due_date,
                "assignee": section.assignee,
                "tasks": [{"description": task.description, "is_checked": task.is_checked} for task in section.tasks],
            }
            for section in sections
        ],
    )


@router.get("/{record_id}/export")
async def export_rci_plan(record_id: str) -> Response:
    """The real .docx download for "Accept and Push to TW" (RciPlanPage.tsx)
    — fills the company's actual RCI Plan template (assets/rci_plan_template.docx)
    with this investigation's persisted sections, per the user (2026-07-31)."""
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

    persisted = await fetch_rci_sections(deviation_id)
    if not persisted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    extended = event_type == "Deviation"
    trackwise_fields = build_trackwise_fields(row, row["qe_type"], extended=extended)
    sections = [RciSectionItem(**section) for section in persisted]

    docx_bytes, truncated = build_rci_plan_docx(record_id, trackwise_fields, sections)
    if truncated:
        logger.warning(
            "RCI plan export for record_id=%s has %d section(s) beyond the template's %d-slot capacity — dropped",
            record_id, truncated, len(sections) - truncated,
        )

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="RCI_Plan_{record_id}.docx"'},
    )


@router.get("/{record_id}", response_model=RciPlanRecord)
async def get_rci_plan(record_id: str) -> RciPlanRecord:
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

    # Deviation gets the extended field set only for rci-plan.
    extended = event_type == "Deviation"
    persisted = await fetch_rci_sections(deviation_id)
    return RciPlanRecord(
        record_id=record_id,
        event_type=event_type,
        trackwise_fields=build_trackwise_fields(row, row["qe_type"], extended=extended),
        sections=[RciSectionItem(**section) for section in persisted] if persisted else None,
        stage=stage_for(row["status"]),
    )
