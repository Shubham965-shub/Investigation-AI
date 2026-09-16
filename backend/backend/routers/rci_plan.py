from __future__ import annotations

import datetime
import logging

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from backend.clients.ds_client import _raise_for_upstream_error, ds_post, get_client, raise_for_ds_request_error
from backend.db.auth_queries import fetch_user_by_username
from backend.db.field_mapping import build_trackwise_fields, resolved_event_type
from backend.db.generated_content_queries import fetch_problem_statement, fetch_rci_sections, replace_rci_sections
from backend.db.module_stage import stage_for
from backend.db.queries import fetch_investigation_row, fetch_open_investigators
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


def _add_working_days(start: datetime.date, days: int) -> datetime.date:
    """Skips weekends only — no holiday calendar is tracked."""
    current = start
    added = 0
    while added < days:
        current += datetime.timedelta(days=1)
        if current.weekday() < 5:  # Monday=0 .. Friday=4
            added += 1
    return current


@router.post("/{record_id}/generate", response_model=RciPlanGenerateResponse)
async def generate_rci_plan(record_id: str, request: RciPlanGenerateRequest) -> RciPlanGenerateResponse:
    # Use the generated Problem Statement as "description", falling back to the raw TrackWise
    # column if none has been generated yet.
    try:
        problem_statement = await fetch_problem_statement(int(record_id))
    except ValueError:
        problem_statement = None
    if problem_statement:
        request.trackwise_fields["description"] = problem_statement

    data = await ds_post("/rci/plan", json=request.model_dump())
    response = RciPlanGenerateResponse(**data)

    # TCD defaults to generation day + 5 working days, editable per-section afterward. Set on the
    # response itself so the frontend shows it immediately without a reload.
    default_due_date = _add_working_days(datetime.datetime.now(datetime.timezone.utc).date(), 5).isoformat()

    # Assignee defaults to the investigation's own investigator, if any (still editable).
    default_assignee = None
    try:
        row = await fetch_investigation_row(int(record_id))
        if row:
            default_assignee = row["investigator"]
    except ValueError:
        pass

    for section in response.sections:
        section.due_date = default_due_date
        section.assignee = default_assignee

    # Persisting is best-effort; a DB issue must not break generation itself.
    try:
        deviation_id = int(record_id)
        await replace_rci_sections(
            deviation_id,
            [
                {
                    "title": section.title,
                    "correlation": section.correlation,
                    "due_date": default_due_date,
                    "assignee": default_assignee,
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
    except httpx.HTTPStatusError as exc:
        _raise_for_upstream_error(exc)
    except httpx.RequestError as exc:
        raise_for_ds_request_error(exc)
    return RciTemplateUploadResponse(**response.json())


@router.put("/{record_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def update_rci_plan(record_id: str, sections: list[RciSectionItem]) -> None:
    """Full replace of the persisted sections."""
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    if await any_task_critique_started(deviation_id):
        # replace_rci_sections deletes-then-recreates every section row (new IDs), which would
        # cascade-delete Task Critique history once a report exists against a section.
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
    """Fills the RCI Plan .docx template and returns it; also persists a frozen approval snapshot
    (best-effort — must not block the download) that a separate process pushes into Trackwise."""
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
    # Same substitution as generate_rci_plan — show the generated Problem Statement, not raw TrackWise description.
    problem_statement = await fetch_problem_statement(deviation_id)
    if problem_statement:
        trackwise_fields["description"] = problem_statement
    sections = [RciSectionItem(**section) for section in persisted]

    docx_bytes, truncated, owners_truncated = build_rci_plan_docx(record_id, trackwise_fields, sections)
    if truncated:
        # Sections beyond the template's 6-slot task table are dropped entirely.
        logger.warning(
            "RCI plan export for record_id=%s has %d section(s) beyond the template's 6-slot task table capacity — dropped",
            record_id, truncated,
        )
    if owners_truncated:
        # Tasks themselves aren't dropped — only the Sign-off row's 4 Task Owner slots are capped.
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


@router.get("/investigators", response_model=list[str])
async def get_open_investigators() -> list[str]:
    """Investigators on an OPEN investigation only. Must stay registered before /{record_id}, or that catch-all route shadows this one (FastAPI matches by registration order)."""
    return await fetch_open_investigators()


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
    trackwise_fields = build_trackwise_fields(row, row["qe_type"], extended=extended)
    # Same substitution as generate_rci_plan/export_rci_plan — frontend reads this back as prefill.
    problem_statement = await fetch_problem_statement(deviation_id)
    if problem_statement:
        trackwise_fields["description"] = problem_statement
    return RciPlanRecord(
        record_id=record_id,
        event_type=event_type,
        trackwise_fields=trackwise_fields,
        sections=[RciSectionItem(**section) for section in persisted] if persisted else None,
        stage=stage_for(row["status"]),
        locked_for_editing=await any_task_critique_started(deviation_id),
    )
