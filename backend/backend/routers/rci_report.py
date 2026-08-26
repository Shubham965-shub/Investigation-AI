from __future__ import annotations

import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.clients.ds_client import ds_post
from backend.db.auth_queries import fetch_user_by_username
from backend.db.field_mapping import build_trackwise_fields, resolved_event_type
from backend.db.generated_content_queries import fetch_rci_sections
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
from backend.routers.auth import get_current_username
from backend.schemas.rci_report import RciReportRecord, RciReportSections
from backend.services.rci_report_export import build_rci_report_docx
from backend.services.rci_report_request import build_rci_report_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rci-report", tags=["RCI Report"])

_NOT_FOUND_DETAIL = "No investigation found for this record"


@router.get("/{record_id}", response_model=RciReportRecord)
async def get_rci_report(record_id: str) -> RciReportRecord:
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

    stored = await fetch_rci_report(deviation_id)
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


@router.put("/{record_id}/inputs", response_model=RciReportRecord)
async def update_rci_report_inputs(record_id: str, request: RciReportInputsRequest) -> RciReportRecord:
    """Persists the mc_confirmed toggle / manual entries as the investigator
    fills them in, independent of generation itself — lets these survive a
    page reload before the first "Generate" click."""
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    await save_rci_report_inputs(deviation_id, request.mc_confirmed, request.manual_entries)
    return await get_rci_report(record_id)


@router.post("/{record_id}/generate", response_model=RciReportRecord)
async def generate_rci_report(record_id: str) -> RciReportRecord:
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

    stored = await fetch_rci_report(deviation_id)
    rci_sections = await fetch_rci_sections(deviation_id)
    task_critique_reports = await fetch_reports_by_task_index(deviation_id)
    rc_capa_reports = await fetch_rc_capa_reports(deviation_id)
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

    await save_rci_report(
        deviation_id,
        report.model_dump(),
        stored["mc_confirmed"] if stored else None,
        stored["manual_entries"] if stored else {},
    )

    return await get_rci_report(record_id)


@router.put("/{record_id}", response_model=RciReportRecord)
async def update_rci_report(record_id: str, request: RciReportSections) -> RciReportRecord:
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    stored = await fetch_rci_report(deviation_id)
    if stored is None or stored["report"] is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No RCI Report has been generated yet")

    await update_rci_report_sections(deviation_id, request.model_dump())
    return await get_rci_report(record_id)


@router.get("/{record_id}/export")
async def export_rci_report(record_id: str, username: str = Depends(get_current_username)) -> Response:
    """The real .docx download for "Accept and Push to TW" (RciReportPage.tsx)
    — fills the company's actual RCI Report template
    (assets/rci_report_template.docx) with this investigation's persisted
    report, per the user (2026-08-25). A section ds couldn't generate (see
    RciReportSections.errors) shows up in the document as an explicit
    "could not be generated" note rather than a silent gap — see
    services/rci_report_export.py's module docstring for the full mapping.

    Also persists this generated docx to investigation_rci_report_exports as
    a frozen approval snapshot, same convention as RCI Plan's own export —
    best-effort, since a persistence failure must never break the download
    the user is actively waiting on."""
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

    stored = await fetch_rci_report(deviation_id)
    if stored is None or stored["report"] is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No RCI Report has been generated yet")

    trackwise_fields = build_trackwise_fields(row, row["qe_type"], extended=event_type == "Deviation", for_rci_report=True)
    report = RciReportSections(**stored["report"])
    docx_bytes = build_rci_report_docx(record_id, trackwise_fields, report)

    try:
        approver = await fetch_user_by_username(username)
        await insert_rci_report_export(deviation_id, docx_bytes, approver["id"] if approver else None)
    except Exception:
        logger.warning("Could not persist RCI report export snapshot for record_id=%s", record_id, exc_info=True)

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="RCI_Report_{record_id}.docx"'},
    )
