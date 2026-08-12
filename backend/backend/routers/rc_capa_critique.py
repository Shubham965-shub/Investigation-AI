from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from backend.clients.ds_client import _raise_for_upstream_error, get_client
from backend.db.auth_queries import fetch_user_by_username
from backend.db.critique_state import MAX_UPLOADS
from backend.db.field_mapping import resolved_event_type
from backend.db.queries import fetch_investigation_row
from backend.db.rc_capa_critique_queries import (
    compute_rc_capa_state,
    fetch_report_file_bytes,
    fetch_rc_capa_reports,
    insert_report,
    save_critiques,
    set_recommendation_decision,
    set_rc_capa_scores,
)
from backend.db.rc_capa_sit_review_queries import fetch_latest_sit_review_status, insert_sit_review
from backend.routers.auth import get_current_username
from backend.schemas.rc_capa_critique import RcCapaState, RecommendationDecisionRequest

logger = logging.getLogger(__name__)

_NOT_FOUND_DETAIL = "No investigation found for this record"

router = APIRouter(prefix="/rc-capa-critique", tags=["RC & CAPA Critique"])


async def _call_critique_endpoint(
    client: httpx.AsyncClient, path: str, event_type: str, filename: str | None, file_bytes: bytes, content_type: str | None
) -> Dict[str, Any]:
    try:
        response = await client.post(
            path,
            params={"event_type": event_type},
            files={"file": (filename, file_bytes, content_type)},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        _raise_for_upstream_error(exc)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"InvestigationAi_DS service unreachable: {exc}",
        ) from exc
    return response.json()


def _section_percentage(sections: Dict[str, Any], *keys: str) -> "int | None":
    """Combines one or more of DS's rubric sections (each a SectionScore:
    marks_awarded/applicable_max/percentage) into one percentage, summing
    marks and denominators across the given keys before dividing — this is
    what lets rc_score merge the 'rc' and 'impact' sections into one figure
    rather than just using either section's own percentage in isolation."""
    present = [sections[k] for k in keys if sections.get(k)]
    if not present:
        return None
    marks = sum(s["marks_awarded"] for s in present)
    max_ = sum(s["applicable_max"] for s in present)
    if max_ <= 0:
        return None
    return round(marks / max_ * 100)


async def _score_rc_capa_report(
    event_type: str, filename: str | None, file_bytes: bytes, content_type: str | None
) -> "tuple[int | None, int | None, int | None]":
    """Scores the final (locked) report against DS's rubric-based /score/report
    endpoint and returns (rc_score, capa_score, total_score) — rc_score
    combines the 'rc' and 'impact' rubric sections (matching this module's
    own "RC Impact Assessment Critique" category, which already bundles the
    two together everywhere else); capa_score is the 'capa' section alone;
    total_score combines all three (2026-08-07, per the user: the underlying
    raw marks added together, divided by their combined max — not a naive
    average of rc_score and capa_score). Column split matches
    investigation_rc_capa_reports as already created against the live DB
    (2026-08-07). Best-effort, same as routers/task_critique.py's
    _score_task_report — a scoring failure must not undo an upload that
    already succeeded and persisted."""
    client = get_client()
    try:
        response = await client.post(
            "/score/report",
            data={"event_type": event_type},
            files={"file": (filename, file_bytes, content_type)},
        )
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("RC & CAPA report scoring failed for %s", filename, exc_info=True)
        return None, None, None
    sections = response.json().get("sections") or {}
    rc_score = _section_percentage(sections, "rc", "impact")
    capa_score = _section_percentage(sections, "capa")
    total_score = _section_percentage(sections, "rc", "impact", "capa")
    return rc_score, capa_score, total_score


def _find_recommendation(reports: List[Dict[str, Any]], recommendation_id: int) -> bool:
    if not reports:
        return False
    for critique in reports[-1]["critiques"]:
        if any(r["id"] == recommendation_id for r in critique["recommendations"]):
            return True
    return False


async def _build_state(record_id: str, deviation_id: int) -> RcCapaState:
    reports = await fetch_rc_capa_reports(deviation_id)
    state = compute_rc_capa_state(reports)
    sit_review_status = await fetch_latest_sit_review_status(deviation_id)
    return RcCapaState(
        record_id=record_id,
        status=state["status"],
        upload_count=state["upload_count"],
        locked=state["locked"],
        next_upload_is_final=state["next_upload_is_final"],
        can_upload=state["can_upload"],
        latest_report=state["latest"],
        sit_review_status=sit_review_status,
    )


async def _deviation_id_and_row(record_id: str):
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

    return deviation_id, row, event_type


@router.get("/{record_id}", response_model=RcCapaState)
async def get_rc_capa_critique(record_id: str) -> RcCapaState:
    deviation_id, _row, _event_type = await _deviation_id_and_row(record_id)
    return await _build_state(record_id, deviation_id)


@router.post("/{record_id}/upload", response_model=RcCapaState)
async def upload_rc_capa_report(record_id: str, file: UploadFile) -> RcCapaState:
    deviation_id, _row, event_type = await _deviation_id_and_row(record_id)
    reports = await fetch_rc_capa_reports(deviation_id)
    state = compute_rc_capa_state(reports)

    if state["locked"] or not state["can_upload"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This report cannot be uploaded/reuploaded right now",
        )

    attempt_number = state["upload_count"] + 1
    is_gospel = state["next_upload_is_final"]
    file_bytes = await file.read()

    if is_gospel:
        report_id = await insert_report(deviation_id, attempt_number, file.filename or "report", file_bytes, is_gospel=True)
        # A gospel report is final the moment it's uploaded — score it now
        # (2026-08-07, per the user), same trigger as Task Critique's.
        rc_score, capa_score, total_score = await _score_rc_capa_report(event_type, file.filename, file_bytes, file.content_type)
        await set_rc_capa_scores(report_id, rc_score, capa_score, total_score)
        return await _build_state(record_id, deviation_id)

    # Real DS endpoints (per the user, 2026-08-06: module 6/RC & CAPA Critique
    # uses these two single-purpose endpoints, not the combined
    # /critique/critique-rc-conclusion-and-capa (used by neither module now —
    # module 5/Task Critique calls the genuinely per-task
    # /critique/analyse-task-report instead, see routers/task_critique.py) —
    # called BEFORE persisting anything, so a transient DS failure doesn't
    # burn one of the 3 real upload attempts.
    client = get_client()
    rc_conclusion, capa = await asyncio.gather(
        _call_critique_endpoint(client, "/critique/critique-rc-conclusion", event_type, file.filename, file_bytes, file.content_type),
        _call_critique_endpoint(client, "/critique/critique-capa", event_type, file.filename, file_bytes, file.content_type),
    )

    report_id = await insert_report(deviation_id, attempt_number, file.filename or "report", file_bytes, is_gospel=False)
    await save_critiques(
        report_id,
        rc_conclusion_text=rc_conclusion["rc_conclusion_text"],
        rc_recommendations=rc_conclusion["recommendations"],
        rc_strengths=rc_conclusion["strengths"],
        capa_recommendations=capa["recommendations"],
        capa_strengths=capa["strengths"],
    )

    # The 3rd attempt is final regardless of decision mix (see
    # critique_state.compute_upload_state) — score it now, since no further
    # upload will ever supersede it.
    if attempt_number >= MAX_UPLOADS:
        rc_score, capa_score, total_score = await _score_rc_capa_report(event_type, file.filename, file_bytes, file.content_type)
        await set_rc_capa_scores(report_id, rc_score, capa_score, total_score)

    return await _build_state(record_id, deviation_id)


@router.post("/{record_id}/recommendations/{recommendation_id}/decision", response_model=RcCapaState)
async def decide_rc_capa_recommendation(
    record_id: str, recommendation_id: int, request: RecommendationDecisionRequest
) -> RcCapaState:
    if request.decision == "rejected" and not request.reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A reason is required to reject a recommendation")

    deviation_id, _row, _event_type = await _deviation_id_and_row(record_id)
    reports = await fetch_rc_capa_reports(deviation_id)
    state = compute_rc_capa_state(reports)

    if state["locked"] or state["latest"] is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This step is locked and no longer accepts decisions")

    if not _find_recommendation(reports, recommendation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such recommendation on the current report")

    await set_recommendation_decision(state["latest"]["id"], recommendation_id, request.decision, request.reason)
    return await _build_state(record_id, deviation_id)


@router.post("/{record_id}/push-to-sit-review", response_model=RcCapaState)
async def push_rc_capa_to_sit_review(record_id: str, username: str = Depends(get_current_username)) -> RcCapaState:
    deviation_id, _row, _event_type = await _deviation_id_and_row(record_id)
    reports = await fetch_rc_capa_reports(deviation_id)
    state = compute_rc_capa_state(reports)

    if state["status"] != "complete":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RC & CAPA Critique isn't complete yet")

    latest = state["latest"]
    docx = await fetch_report_file_bytes(latest["id"])
    if docx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No report file found to push")

    try:
        approver = await fetch_user_by_username(username)
        await insert_sit_review(deviation_id, docx=docx, approved_by=approver["id"] if approver else None)
    except Exception:
        logger.warning("Could not persist RC & CAPA SIT review snapshot for record_id=%s", record_id, exc_info=True)

    return await _build_state(record_id, deviation_id)