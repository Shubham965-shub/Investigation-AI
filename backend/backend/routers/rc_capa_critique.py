from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from backend.clients.ds_client import HEAVY_DS_TIMEOUT, _raise_for_upstream_error, get_client, raise_for_ds_request_error
from backend.db.auth_queries import fetch_user_by_username
from backend.db.critique_state import MAX_UPLOADS
from backend.db.field_mapping import normalize_rci_id, resolved_event_type
from backend.db.generated_content_queries import fetch_problem_statement
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
from backend.routers.auth import get_current_payload, get_current_username
from backend.schemas.rc_capa_critique import RcCapaReport, RcCapaState, RecommendationDecisionRequest

logger = logging.getLogger(__name__)

_NOT_FOUND_DETAIL = "No investigation found for this record"

router = APIRouter(prefix="/rc-capa-critique", tags=["RC, Impact & CAPA Critique"])


async def _call_critique_endpoint(
    client: httpx.AsyncClient,
    path: str,
    event_type: str,
    problem_statement: str,
    filename: str | None,
    file_bytes: bytes,
    content_type: str | None,
    previous_recommendations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    try:
        response = await client.post(
            path,
            params={
                "event_type": event_type,
                "problem_statement": problem_statement,
                "previous_recommendations": json.dumps(previous_recommendations or []),
            },
            files={"file": (filename, file_bytes, content_type)},
            timeout=HEAVY_DS_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        _raise_for_upstream_error(exc)
    except httpx.RequestError as exc:
        raise_for_ds_request_error(exc)
    return response.json()


def _section_percentage(sections: Dict[str, Any], *keys: str) -> "int | None":
    """Sums marks/denominators across the given rubric sections before dividing, so a merged score isn't just an average of each section's own percentage."""
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
) -> "tuple[int | None, int | None, int | None, int | None, list[dict]]":
    """Scores the locked report via DS's /score/report; rc_score and impact_score are shown as
    separate badges (ds scores them as separate rubric sections), total_score combines all three.
    Best-effort — a scoring failure must not undo an upload that already succeeded."""
    client = get_client()
    try:
        response = await client.post(
            "/score/report",
            data={"event_type": event_type},
            files={"file": (filename, file_bytes, content_type)},
            timeout=HEAVY_DS_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("RC & CAPA report scoring failed for %s", filename, exc_info=True)
        return None, None, None, None, []
    data = response.json()
    sections = data.get("sections") or {}
    rc_score = _section_percentage(sections, "rc")
    impact_score = _section_percentage(sections, "impact")
    capa_score = _section_percentage(sections, "capa")
    total_score = _section_percentage(sections, "rc", "impact", "capa")
    info = data.get("info") or []
    return rc_score, impact_score, capa_score, total_score, info


def _find_recommendation(reports: List[Dict[str, Any]], recommendation_id: int) -> bool:
    if not reports:
        return False
    for critique in reports[-1]["critiques"]:
        if any(r["id"] == recommendation_id for r in critique["recommendations"]):
            return True
    return False


async def _build_state(record_id: str, deviation_id: int, rci_id: Optional[str], row: Any = None) -> RcCapaState:
    reports = await fetch_rc_capa_reports(deviation_id, rci_id=rci_id)
    state = compute_rc_capa_state(reports)
    sit_review_status = await fetch_latest_sit_review_status(deviation_id, rci_id=rci_id)
    if row is None:
        row = await fetch_investigation_row(deviation_id, rci_id=rci_id)
    return RcCapaState(
        record_id=record_id,
        status=state["status"],
        upload_count=state["upload_count"],
        locked=state["locked"],
        next_upload_is_final=state["next_upload_is_final"],
        can_upload=state["can_upload"],
        latest_report=state["latest"],
        sit_review_status=sit_review_status,
        investigator=row["investigator"] if row else None,
        due_date=row["due_date"].strftime("%d/%m/%Y") if row and row["due_date"] else None,
    )


async def _deviation_id_and_row(record_id: str, rci_id: Optional[str]):
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    row = await fetch_investigation_row(deviation_id, rci_id=rci_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    event_type = resolved_event_type(row["qe_type"])
    if event_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)

    return deviation_id, row, event_type


@router.get("/{record_id}/{rci_id}", response_model=RcCapaState)
async def get_rc_capa_critique(record_id: str, rci_id: str) -> RcCapaState:
    resolved_rci_id = normalize_rci_id(rci_id)
    deviation_id, row, _event_type = await _deviation_id_and_row(record_id, resolved_rci_id)
    return await _build_state(record_id, deviation_id, resolved_rci_id, row)


@router.get("/{record_id}/{rci_id}/history", response_model=List[RcCapaReport])
async def get_rc_capa_history(record_id: str, rci_id: str) -> List[RcCapaReport]:
    """Full audit trail across every attempt, newest first; fetch_rc_capa_reports itself stays ascending since compute_rc_capa_state relies on reports[-1] being the latest."""
    resolved_rci_id = normalize_rci_id(rci_id)
    deviation_id, _row, _event_type = await _deviation_id_and_row(record_id, resolved_rci_id)
    reports = await fetch_rc_capa_reports(deviation_id, rci_id=resolved_rci_id)
    return [RcCapaReport(**report) for report in reversed(reports)]


@router.post("/{record_id}/{rci_id}/upload", response_model=RcCapaState)
async def upload_rc_capa_report(
    record_id: str, rci_id: str, file: UploadFile, claims: dict = Depends(get_current_payload)
) -> RcCapaState:
    resolved_rci_id = normalize_rci_id(rci_id)
    deviation_id, row, event_type = await _deviation_id_and_row(record_id, resolved_rci_id)
    reports = await fetch_rc_capa_reports(deviation_id, rci_id=resolved_rci_id)
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
        report_id = await insert_report(
            deviation_id, attempt_number, file.filename or "report", file_bytes,
            is_gospel=True, uploaded_by=claims.get("uid"), rci_id=resolved_rci_id,
        )
        # A gospel report is final the moment it's uploaded — score it now.
        rc_score, impact_score, capa_score, total_score, score_breakdown = await _score_rc_capa_report(event_type, file.filename, file_bytes, file.content_type)
        await set_rc_capa_scores(report_id, rc_score, impact_score, capa_score, total_score, score_breakdown)
        return await _build_state(record_id, deviation_id, resolved_rci_id, row)

    # Called BEFORE persisting anything, so a transient DS failure doesn't burn one of the 3 real
    # upload attempts. problem_statement lets DS reject a mismatched upload with a 422 up front.
    problem_statement = await fetch_problem_statement(deviation_id, rci_id=resolved_rci_id) or row["description"] or row["title"]

    # Carry forward the previous attempt's accepted-but-still-pending recommendations so DS can
    # check whether this upload actually addresses them.
    previous_rc_recommendations: List[str] = []
    previous_capa_recommendations: List[str] = []
    if reports:
        for critique in reports[-1]["critiques"]:
            accepted = [r["description"] for r in critique["recommendations"] if r["decision"] == "accepted"]
            if critique["category"] == "rc_impact":
                previous_rc_recommendations = accepted
            elif critique["category"] == "capa":
                previous_capa_recommendations = accepted

    client = get_client()
    rc_conclusion, capa = await asyncio.gather(
        _call_critique_endpoint(
            client, "/critique/critique-rc-conclusion", event_type, problem_statement,
            file.filename, file_bytes, file.content_type, previous_recommendations=previous_rc_recommendations,
        ),
        _call_critique_endpoint(
            client, "/critique/critique-capa", event_type, problem_statement,
            file.filename, file_bytes, file.content_type, previous_recommendations=previous_capa_recommendations,
        ),
    )

    report_id = await insert_report(
        deviation_id, attempt_number, file.filename or "report", file_bytes,
        is_gospel=False, uploaded_by=claims.get("uid"), rci_id=resolved_rci_id,
    )
    # rc_recommendations and impact_recommendations are kept as separate lists so the frontend
    # can render them as separate subsections.
    await save_critiques(
        report_id,
        rc_recommendations=rc_conclusion["rc_recommendations"],
        impact_recommendations=rc_conclusion["impact_recommendations"],
        rc_summary=rc_conclusion["rc_conclusion_text"],
        capa_recommendations=capa["recommendations"],
        capa_summary=capa["capa_text"],
        rc_conclusion_text_raw=rc_conclusion.get("rc_conclusion_text_raw", ""),
        is_repeat_occurrence=rc_conclusion.get("is_repeat_occurrence"),
        impact_assessment_text=rc_conclusion.get("impact_assessment_text", ""),
        impact_conclusion_text=rc_conclusion.get("impact_conclusion_text", ""),
        correction_remedial_text=capa.get("correction_remedial_text", ""),
        capa_text_raw=capa.get("capa_text_raw", ""),
        capa_items=capa.get("capa_items", []),
    )

    # The 3rd attempt is final regardless of decision mix — score it now.
    if attempt_number >= MAX_UPLOADS:
        rc_score, impact_score, capa_score, total_score, score_breakdown = await _score_rc_capa_report(event_type, file.filename, file_bytes, file.content_type)
        await set_rc_capa_scores(report_id, rc_score, impact_score, capa_score, total_score, score_breakdown)
    elif not (rc_conclusion["rc_recommendations"] + rc_conclusion["impact_recommendations"] + capa["recommendations"]):
        # Zero recommendations across the board locks this attempt as complete immediately
        # (same as rejecting every recommendation), so it needs the same "score it now" trigger.
        rc_score, impact_score, capa_score, total_score, score_breakdown = await _score_rc_capa_report(event_type, file.filename, file_bytes, file.content_type)
        await set_rc_capa_scores(report_id, rc_score, impact_score, capa_score, total_score, score_breakdown)

    return await _build_state(record_id, deviation_id, resolved_rci_id, row)


@router.post("/{record_id}/{rci_id}/recommendations/{recommendation_id}/decision", response_model=RcCapaState)
async def decide_rc_capa_recommendation(
    record_id: str, rci_id: str, recommendation_id: int, request: RecommendationDecisionRequest
) -> RcCapaState:
    resolved_rci_id = normalize_rci_id(rci_id)
    if request.decision == "rejected" and not request.reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A reason is required to reject a recommendation")

    deviation_id, row, _event_type = await _deviation_id_and_row(record_id, resolved_rci_id)
    reports = await fetch_rc_capa_reports(deviation_id, rci_id=resolved_rci_id)
    state = compute_rc_capa_state(reports)

    if state["locked"] or state["latest"] is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This step is locked and no longer accepts decisions")

    if not _find_recommendation(reports, recommendation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such recommendation on the current report")

    await set_recommendation_decision(state["latest"]["id"], recommendation_id, request.decision, request.reason)

    reports = await fetch_rc_capa_reports(deviation_id, rci_id=resolved_rci_id)
    new_state = compute_rc_capa_state(reports)
    if new_state["status"] == "complete" and new_state["latest"]["total_score"] is None:
        # Rejecting every recommendation just locked this report immediately — score it now.
        report_id = new_state["latest"]["id"]
        file_bytes = await fetch_report_file_bytes(report_id)
        if file_bytes is not None:
            _, _, event_type = await _deviation_id_and_row(record_id, resolved_rci_id)
            rc_score, impact_score, capa_score, total_score, score_breakdown = await _score_rc_capa_report(
                event_type, new_state["latest"]["file_name"], file_bytes, None
            )
            await set_rc_capa_scores(report_id, rc_score, impact_score, capa_score, total_score, score_breakdown)

    return await _build_state(record_id, deviation_id, resolved_rci_id, row)


@router.post("/{record_id}/{rci_id}/push-to-sit-review", response_model=RcCapaState)
async def push_rc_capa_to_sit_review(record_id: str, rci_id: str, username: str = Depends(get_current_username)) -> RcCapaState:
    resolved_rci_id = normalize_rci_id(rci_id)
    deviation_id, row, _event_type = await _deviation_id_and_row(record_id, resolved_rci_id)
    reports = await fetch_rc_capa_reports(deviation_id, rci_id=resolved_rci_id)
    state = compute_rc_capa_state(reports)

    if state["latest"] is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No RC, Impact & CAPA Critique report has been uploaded yet")

    latest = state["latest"]
    docx = await fetch_report_file_bytes(latest["id"])
    if docx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No report file found to push")

    try:
        approver = await fetch_user_by_username(username)
        await insert_sit_review(deviation_id, docx=docx, approved_by=approver["id"] if approver else None, rci_id=resolved_rci_id)
    except Exception:
        logger.warning("Could not persist RC & CAPA SIT review snapshot for record_id=%s", record_id, exc_info=True)

    return await _build_state(record_id, deviation_id, resolved_rci_id, row)
