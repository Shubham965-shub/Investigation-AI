from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from backend.clients.ds_client import ds_post, get_client
from backend.db.auth_queries import fetch_user_by_username
from backend.db.field_mapping import build_trackwise_fields, resolved_event_type
from backend.db.generated_content_queries import fetch_rci_sections, replace_rci_sections
from backend.db.module_stage import stage_for
from backend.db.queries import fetch_investigation_row
from backend.db.rci_plan_export_queries import insert_rci_plan_export
from backend.db.task_critique_queries import any_task_critique_started
from backend.routers.auth import get_current_username
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

    if await any_task_critique_started(deviation_id):
        # replace_rci_sections deletes-then-recreates every section row (new
        # IDs) — once Task Critique has a report against a section, further
        # edits here would cascade-delete that history (2026-08-05, per the
        # user: lock RCI Plan editing instead of letting that happen).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RCI Plan is locked because Task Critique has already started",
        )

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
async def export_rci_plan(record_id: str, username: str = Depends(get_current_username)) -> Response:
    """The real .docx download for "Accept and Push to TW" (RciPlanPage.tsx)
    — fills the company's actual RCI Plan template (assets/rci_plan_template.docx)
    with this investigation's persisted sections, per the user (2026-07-31).

    Also persists this generated docx to investigation_rci_plan_exports
    (2026-08-04, per the user) as a frozen approval snapshot — a separate,
    external process is expected to pick up 'pending' rows there and push
    them into Trackwise. Best-effort: a persistence failure must never break
    the download the user is actively waiting on."""
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

    docx_bytes, truncated, owners_truncated = build_rci_plan_docx(record_id, trackwise_fields, sections)
    if truncated:
        # Actually dropped from the Investigation tasks table entirely — the
        # template's 6-slot capacity, same constraint the old template had.
        logger.warning(
            "RCI plan export for record_id=%s has %d section(s) beyond the template's 6-slot task table capacity — dropped",
            record_id, truncated,
        )
    if owners_truncated:
        # NOT dropped — every section's tasks still appear in full in the
        # Investigation tasks table. Only the Sign-off row's 4 Task Owner
        # slots are capped, so sections beyond that just have no named
        # owner there.
        logger.warning(
            "RCI plan export for record_id=%s has %d section(s) beyond the Sign-off row's 4 Task Owner slots — no named owner for those",
            record_id, owners_truncated,
        )

    try:
        approver = await fetch_user_by_username(username)
        await insert_rci_plan_export(
            deviation_id=deviation_id,
            docx=docx_bytes,
            truncated_sections=truncated,
            approved_by=approver["id"] if approver else None,
        )
    except Exception:
        logger.warning("Could not persist RCI plan export snapshot for record_id=%s", record_id, exc_info=True)

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
        locked_for_editing=await any_task_critique_started(deviation_id),
    )
