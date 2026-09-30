from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.clients.ds_client import ds_post
from backend.db.auth_queries import fetch_user_by_username
from backend.db.field_mapping import build_trackwise_fields, normalize_rci_id, resolved_event_type
from backend.db.generated_content_queries import fetch_problem_statement, fetch_rci_sections
from backend.db.queries import fetch_investigation_row
from backend.db.rc_capa_critique_queries import fetch_rc_capa_reports
from backend.db.rci_report_export_queries import insert_rci_report_export
from backend.db.rci_report_queries import (
    fetch_rci_report,
    save_rci_report,
    save_rci_report_inputs,
    update_rci_report_sections,
)
from backend.db.task_critique_queries import fetch_reports_by_task_index
from backend.routers.auth import get_current_payload, get_current_username
from backend.schemas.rci_report import RciReportRecord, RciReportSections
from backend.services.rci_report_export import build_rci_report_docx
from backend.services.rci_report_request import build_rci_report_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rci-report", tags=["RCI Report"])

_NOT_FOUND_DETAIL = "No investigation found for this record"


@router.get("/{record_id}/{rci_id}", response_model=RciReportRecord)
async def get_rci_report(record_id: str, rci_id: str) -> RciReportRecord:
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

    stored = await fetch_rci_report(deviation_id, rci_id=resolved_rci_id)
    return RciReportRecord(
        record_id=record_id,
        event_type=event_type,
        trackwise_fields=build_trackwise_fields(row, row["qe_type"], extended=event_type == "Deviation", for_rci_report=True),
        report=stored["report"] if stored else None,
        generated_at=stored["generated_at"] if stored else None,
        mc_confirmed=stored["mc_confirmed"] if stored else None,
        manual_entries=stored["manual_entries"] if stored else {},
    )


class RciReportInputsRequest(BaseModel):
    mc_confirmed: Optional[bool] = None
    manual_entries: Dict[str, str] = Field(default_factory=dict)


@router.put("/{record_id}/{rci_id}/inputs", response_model=RciReportRecord)
async def update_rci_report_inputs(record_id: str, rci_id: str, request: RciReportInputsRequest) -> RciReportRecord:
    """Persists mc_confirmed/manual_entries independent of generation, so they survive a reload before the first "Generate" click."""
    resolved_rci_id = normalize_rci_id(rci_id)
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    await save_rci_report_inputs(deviation_id, request.mc_confirmed, request.manual_entries, rci_id=resolved_rci_id)
    return await get_rci_report(record_id, rci_id)


@router.post("/{record_id}/{rci_id}/generate", response_model=RciReportRecord)
async def generate_rci_report(record_id: str, rci_id: str, claims: dict = Depends(get_current_payload)) -> RciReportRecord:
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

    stored = await fetch_rci_report(deviation_id, rci_id=resolved_rci_id)
    rci_sections = await fetch_rci_sections(deviation_id, rci_id=resolved_rci_id)
    task_critique_reports = await fetch_reports_by_task_index(deviation_id, rci_id=resolved_rci_id)
    rc_capa_reports = await fetch_rc_capa_reports(deviation_id, rci_id=resolved_rci_id)
    rc_capa_report = rc_capa_reports[-1] if rc_capa_reports else None

    payload = build_rci_report_request(
        record_id=record_id,
        event_type=event_type,
        trackwise_fields=build_trackwise_fields(row, row["qe_type"], extended=event_type == "Deviation", for_rci_report=True),
        rci_sections=rci_sections,
        task_critique_reports=task_critique_reports,
        rc_capa_report=rc_capa_report,
        mc_confirmed=stored["mc_confirmed"] if stored else None,
        manual_entries=stored["manual_entries"] if stored else {},
    )

    data = await ds_post("/rci-report/generate", json=payload)
    report = RciReportSections(**data)

    # Overwrite ds's own re-derived problem_description with the investigator's approved Problem
    # Statement verbatim, so the two don't silently diverge.
    problem_statement = await fetch_problem_statement(deviation_id, rci_id=resolved_rci_id)
    if problem_statement and report.executive_summary:
        report.executive_summary.problem_description = [problem_statement]  # kept as one bullet, not re-segmented

    await save_rci_report(
        deviation_id,
        report.model_dump(),
        stored["mc_confirmed"] if stored else None,
        stored["manual_entries"] if stored else {},
        generated_by=claims.get("uid"),
        rci_id=resolved_rci_id,
    )

    return await get_rci_report(record_id, rci_id)


@router.put("/{record_id}/{rci_id}", response_model=RciReportRecord)
async def update_rci_report(record_id: str, rci_id: str, request: RciReportSections) -> RciReportRecord:
    resolved_rci_id = normalize_rci_id(rci_id)
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    stored = await fetch_rci_report(deviation_id, rci_id=resolved_rci_id)
    if stored is None or stored["report"] is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No RCI Report has been generated yet")

    await update_rci_report_sections(deviation_id, request.model_dump(), rci_id=resolved_rci_id)
    return await get_rci_report(record_id, rci_id)


@router.get("/{record_id}/{rci_id}/export")
async def export_rci_report(record_id: str, rci_id: str, username: str = Depends(get_current_username)) -> Response:
    """Fills the RCI Report .docx template and returns it; a section ds couldn't generate shows an
    explicit "could not be generated" note. Also persists a frozen approval snapshot (best-effort
    — must not block the download), same convention as RCI Plan's export."""
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

    stored = await fetch_rci_report(deviation_id, rci_id=resolved_rci_id)
    if stored is None or stored["report"] is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No RCI Report has been generated yet")

    trackwise_fields = build_trackwise_fields(row, row["qe_type"], extended=event_type == "Deviation", for_rci_report=True)
    report = RciReportSections(**stored["report"])

    # Team Members re-derived fresh at export time (not trusted from whatever was true at
    # generation time) — same "re-fetch, don't trust a stale snapshot" pattern RCI Plan's own
    # export already uses. Investigator first, then each section's distinct assignee.
    team_members: List[Tuple[str, str]] = []
    seen_names = set()
    primary_investigator = trackwise_fields.get("Investigator")
    if primary_investigator:
        team_members.append((primary_investigator, "Investigator"))
        seen_names.add(primary_investigator)
    rci_sections = await fetch_rci_sections(deviation_id, rci_id=resolved_rci_id)
    for section in rci_sections:
        name = section.get("assignee")
        if name and name not in seen_names:
            team_members.append((name, section.get("title") or "Task Owner"))
            seen_names.add(name)

    docx_bytes = build_rci_report_docx(
        record_id, trackwise_fields, report, event_type, team_members, stored["manual_entries"] or {}
    )

    try:
        approver = await fetch_user_by_username(username)
        await insert_rci_report_export(deviation_id, docx_bytes, approver["id"] if approver else None, rci_id=resolved_rci_id)
    except Exception:
        logger.warning("Could not persist RCI report export snapshot for record_id=%s", record_id, exc_info=True)

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="RCI_Report_{record_id}.docx"'},
    )
