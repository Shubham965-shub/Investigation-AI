from __future__ import annotations

import datetime
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from backend.clients.ds_client import ds_post, get_client
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
    """Skips Saturdays/Sundays — no holiday calendar tracked anywhere else in
    this app, so weekends are the only exclusion."""
    current = start
    added = 0
    while added < days:
        current += datetime.timedelta(days=1)
        if current.weekday() < 5:  # Monday=0 .. Friday=4
            added += 1
    return current


@router.post("/{record_id}/generate", response_model=RciPlanGenerateResponse)
async def generate_rci_plan(record_id: str, request: RciPlanGenerateRequest) -> RciPlanGenerateResponse:
    # Use the LLM-generated Problem Statement as the plan's "description"
    # context instead of the raw TrackWise column (2026-08-18, per the user)
    # — falls back to whatever was already in trackwise_fields if no problem
    # statement has been generated yet for this investigation.
    try:
        problem_statement = await fetch_problem_statement(int(record_id))
    except ValueError:
        problem_statement = None
    if problem_statement:
        request.trackwise_fields["description"] = problem_statement

    data = await ds_post("/rci/plan", json=request.model_dump())
    response = RciPlanGenerateResponse(**data)

    # TCD defaults to generation day + 5 working days (per the user,
    # 2026-08-22) — still editable per-section afterward, this just saves the
    # investigator from having to set every section's TCD by hand. Set on the
    # response itself (not just the persisted rows below) so the frontend
    # shows it immediately after generating, without needing a reload.
    default_due_date = _add_working_days(datetime.datetime.now(datetime.timezone.utc).date(), 5).isoformat()

    # Assignee defaults to whoever's already assigned as this investigation's
    # investigator (per the user, 2026-08-24) — same "prefill, still editable"
    # treatment as due_date above, so a case with a real investigator doesn't
    # start every section on "Unassigned" for no reason. None (left blank)
    # when the investigation has no investigator assigned yet.
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
    # Same substitution as generate_rci_plan — the exported docx's "A
    # description of what has happened" paragraph should show the
    # LLM-generated Problem Statement, not the raw TrackWise description
    # column (2026-08-18, per the user).
    problem_statement = await fetch_problem_statement(deviation_id)
    if problem_statement:
        trackwise_fields["description"] = problem_statement
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


@router.get("/investigators", response_model=list[str])
async def get_open_investigators() -> list[str]:
    """Investigators currently assigned to an OPEN investigation only
    (2026-08-19, per the user, re-scoping the prior 2026-08-13 all-time
    list) — populates the Investigator dropdown per section on the RCI Plan
    Creation page, replacing free text. Registered before /{record_id}
    below — otherwise that catch-all route would shadow this one (FastAPI
    matches by registration order; same class of bug fixed in ds's critique
    routes earlier this session)."""
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
    # Same substitution as generate_rci_plan/export_rci_plan — this is what
    # the frontend reads back as prefill and re-sends verbatim on a
    # regenerate, so it needs the Problem Statement text too, not the raw
    # TrackWise description column (2026-08-18, per the user).
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
