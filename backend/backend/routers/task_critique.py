from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from backend.clients.ds_client import HEAVY_DS_TIMEOUT, _raise_for_upstream_error, get_client, raise_for_ds_request_error
from backend.db.critique_state import MAX_UPLOADS
from backend.db.field_mapping import resolved_event_type
from backend.db.generated_content_queries import fetch_problem_statement
from backend.db.queries import fetch_investigation_row
from backend.db.rci_plan_export_queries import fetch_latest_rci_plan_export_docx
from backend.db.task_critique_queries import (
    compute_section_state,
    fetch_recommendation_history,
    fetch_report_file_bytes,
    fetch_reports_by_task_index,
    insert_recommendation_history,
    save_critique,
    set_recommendation_decision,
    set_task_score,
    upsert_report,
)
from backend.db.task_critique_source_document_queries import fetch_source_document, upsert_source_document
from backend.routers.auth import get_current_payload
from backend.schemas.task_critique import (
    RecommendationDecisionRequest,
    RecommendationHistoryAttempt,
    TaskCritiqueListResponse,
    TaskCritiqueReport,
    TaskCritiqueSection,
)
from backend.services.rci_plan_extraction import extract_task_sections
from backend.services.task_report_format import missing_task_report_markers

logger = logging.getLogger(__name__)

_NOT_FOUND_DETAIL = "No investigation found for this record"
_TASK_NOT_FOUND_DETAIL = "No such task for this investigation"

# Mirrors ds's UNADDRESSED_MARKER, so carried-forward recommendations still sort first after flattening.
_UNADDRESSED_MARKER = "Still unaddressed from the previous review."
_MAX_RECOMMENDATIONS = 5

router = APIRouter(prefix="/task-critique", tags=["Task Critique"])


async def _get_source_document(deviation_id: int, record_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """A manually uploaded / externally-fed document is always preferred; the RCI Plan export is only the fallback."""
    uploaded = await fetch_source_document(deviation_id)
    if uploaded is not None:
        return uploaded
    docx = await fetch_latest_rci_plan_export_docx(deviation_id)
    if docx is not None:
        return docx, f"RCI_Plan_{record_id}.docx"
    return None, None


async def _score_task_report(
    event_type: str, filename: Optional[str], file_bytes: bytes, content_type: Optional[str]
) -> "Tuple[Optional[int], List[Dict[str, Any]], bool]":
    """Scores the locked report via DS's /score/report. Best-effort — a scoring failure must not undo an already-persisted upload, but is flagged via critique_failed=True rather than looking like "not scored yet"."""
    client = get_client()
    try:
        response = await client.post(
            "/score/report",
            data={"event_type": event_type},
            files={"file": (filename, file_bytes, content_type)},
            timeout=HEAVY_DS_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        task_report_execution = data.get("task_report_execution")
    except httpx.HTTPError:
        logger.warning("Task report scoring failed for %s", filename, exc_info=True)
        return None, [], True
    except (ValueError, KeyError, TypeError):
        # Malformed 200 response — treat the same as a scoring failure.
        logger.warning("Task report scoring returned a malformed response for %s", filename, exc_info=True)
        return None, [], True
    # DS's /score/report also returns rc/impact/capa tables if detected in the same document —
    # those belong to the separate RC & CAPA Critique score and must not leak in here.
    info = [table for table in (data.get("info") or []) if table.get("section") == "task_report"]
    if not task_report_execution:
        # A 200 with no Task Report section detected still counts as incomplete scoring.
        logger.warning("No task_report_execution section detected for %s — scoring incomplete", filename)
        return None, info, True
    return round(task_report_execution["percentage"]), info, False


def _find_task(sections: List[Dict[str, Any]], task_index: int) -> Dict[str, Any]:
    for section in sections:
        if section["task_index"] == task_index:
            return section
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_TASK_NOT_FOUND_DETAIL)


def _describe_task(section: Dict[str, Any]) -> str:
    """Describes this task/section so DS can check the report addresses it specifically, not just the overall investigation."""
    parts = [f"Task: {section['title']}"]
    if section.get("correlation"):
        parts.append(f"Correlation: {section['correlation']}")
    if section.get("tasks"):
        parts.append("Checklist items:\n" + "\n".join(f"- {t}" for t in section["tasks"]))
    return "\n".join(parts)


def _build_section_response(section: Dict[str, Any]) -> TaskCritiqueSection:
    state = compute_section_state(section["report"])
    latest = state["latest"]
    return TaskCritiqueSection(
        task_index=section["task_index"],
        title=section["title"],
        correlation=section["correlation"],
        task_count=len(section["tasks"]),
        due_date=section["due_date"],
        assignee=section["assignee"],
        status=state["status"],
        upload_count=state["upload_count"],
        locked=state["locked"],
        next_upload_is_final=state["next_upload_is_final"],
        can_upload=state["can_upload"],
        critique_failed=bool(latest.get("critique_failed")) if latest else False,
        latest_report=TaskCritiqueReport(**latest) if latest else None,
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


async def _build_sections(deviation_id: int, docx_bytes: bytes) -> List[Dict[str, Any]]:
    extracted = extract_task_sections(docx_bytes)
    reports_by_index = await fetch_reports_by_task_index(deviation_id)
    return [
        {**ext, "task_index": i, "report": reports_by_index.get(i)}
        for i, ext in enumerate(extracted)
    ]


@router.get("/{record_id}", response_model=TaskCritiqueListResponse)
async def get_task_critique(record_id: str) -> TaskCritiqueListResponse:
    deviation_id, _row, _event_type = await _deviation_id_and_row(record_id)
    docx_bytes, file_name = await _get_source_document(deviation_id, record_id)
    if docx_bytes is None:
        return TaskCritiqueListResponse(record_id=record_id, sections=[], has_source_document=False)

    sections = await _build_sections(deviation_id, docx_bytes)
    return TaskCritiqueListResponse(
        record_id=record_id,
        sections=[_build_section_response(s) for s in sections],
        has_source_document=True,
        source_document_name=file_name,
    )


@router.post("/{record_id}/source-document", response_model=TaskCritiqueListResponse)
async def upload_source_document(record_id: str, file: UploadFile) -> TaskCritiqueListResponse:
    """Manual/externally-fed upload; replaces any prior upload for this investigation."""
    deviation_id, _row, _event_type = await _deviation_id_and_row(record_id)

    file_bytes = await file.read()
    try:
        extracted = extract_task_sections(file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read this document") from exc
    if not extracted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No tasks could be found in this document")

    await upsert_source_document(deviation_id, file.filename or "report.docx", file_bytes)
    return await get_task_critique(record_id)


@router.post("/{record_id}/sections/{task_index}/upload", response_model=TaskCritiqueSection)
async def upload_task_report(
    record_id: str, task_index: int, file: UploadFile, claims: dict = Depends(get_current_payload)
) -> TaskCritiqueSection:
    deviation_id, row, event_type = await _deviation_id_and_row(record_id)
    docx_bytes, _file_name = await _get_source_document(deviation_id, record_id)
    if docx_bytes is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No RCI Plan document found for this investigation yet")

    sections = await _build_sections(deviation_id, docx_bytes)
    section = _find_task(sections, task_index)

    state = compute_section_state(section["report"])
    if state["locked"] or not state["can_upload"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This task's report cannot be uploaded/reuploaded right now",
        )

    attempt_number = state["upload_count"] + 1
    is_gospel = state["next_upload_is_final"]
    file_bytes = await file.read()

    missing_markers = missing_task_report_markers(file_bytes)
    if missing_markers:
        # Rejected outright — no attempt consumed, no critique call.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This document doesn't match the required task report format — please upload the correct report.",
        )

    if is_gospel:
        report_id = await upsert_report(
            deviation_id, task_index, attempt_number, file.filename or "report", file_bytes,
            is_gospel=True, uploaded_by=claims.get("uid"),
        )
        # A gospel report is final the moment it's uploaded — no critique, no further review.
        task_score, score_breakdown, critique_failed = await _score_task_report(event_type, file.filename, file_bytes, file.content_type)
        await set_task_score(report_id, task_score, score_breakdown, critique_failed)
        sections = await _build_sections(deviation_id, docx_bytes)
        return _build_section_response(_find_task(sections, task_index))

    # Called BEFORE persisting anything, so a transient DS failure doesn't burn one of the 3 real upload attempts.
    # All fields go via `data=` (multipart), not `params=` — task_description can be several KB and previously went out as a URL query param, risking "URL too long" against some proxies.
    problem_statement = await fetch_problem_statement(deviation_id) or row["description"] or row["title"]
    task_description = _describe_task(section)

    # Run concurrently with the critique call below (needs only raw bytes, not its response) to cut latency to max(critique_time, scoring_time) instead of the sum.
    score_task: Optional["asyncio.Task[Tuple[Optional[int], List[Dict[str, Any]], bool]]"] = None
    if attempt_number >= MAX_UPLOADS:
        score_task = asyncio.create_task(
            _score_task_report(event_type, file.filename, file_bytes, file.content_type)
        )

    client = get_client()
    try:
        response = await client.post(
            "/critique/analyse-task-report",
            data={
                "problem_statement": problem_statement,
                "event_type": event_type,
                "task_description": task_description,
                "deviation_id": str(deviation_id),
                "task_index": str(task_index),
            },
            files={"file": (file.filename, file_bytes, file.content_type)},
            timeout=HEAVY_DS_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if score_task is not None:
            score_task.cancel()
        _raise_for_upstream_error(exc)
    except httpx.RequestError as exc:
        if score_task is not None:
            score_task.cancel()
        raise_for_ds_request_error(exc)

    data = response.json()
    if data.get("total_tasks_analyzed", 0) == 0:
        # A file can pass the local format check yet still not be a genuine, parseable task report.
        if score_task is not None:
            score_task.cancel()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This document doesn't match the required task report format — please upload the correct report.",
        )

    # ds returns one task_critiques entry per checklist item, each capped at 5 recommendations; re-cap after flattening, keeping still-unaddressed carried-forward items first.
    # Summary is positive-only (strengths) — gaps are surfaced separately via recommendations.
    strengths = [task["strengths"] for task in data.get("task_critiques", []) if task.get("strengths")]
    summary: Optional[str] = " ".join(strengths) if strengths else None
    flattened_recommendations: List[str] = [
        rec
        for task in data.get("task_critiques", [])
        for rec in task.get("recommendations", [])
    ]
    recommendations: List[str] = sorted(
        flattened_recommendations, key=lambda r: not r.startswith(_UNADDRESSED_MARKER)
    )[:_MAX_RECOMMENDATIONS]
    # Stored as-is so RCI Report Section 5 can ground on the report's actual content, not just
    # the strengths-only `summary` above (shared identically across every subtask).
    task_findings: List[Dict[str, Any]] = data.get("task_evidence", [])

    report_id = await upsert_report(
        deviation_id, task_index, attempt_number, file.filename or "report", file_bytes,
        is_gospel=False, uploaded_by=claims.get("uid"),
    )
    await save_critique(report_id, summary, task_score=None, recommendations=recommendations, task_findings=task_findings)
    await insert_recommendation_history(deviation_id, task_index, attempt_number, summary, recommendations)

    # The 3rd attempt is final regardless of decision mix — score it now (the scoring call was
    # already kicked off above concurrently with the critique call, so this just awaits it).
    if score_task is not None:
        task_score, score_breakdown, critique_failed = await score_task
        await set_task_score(report_id, task_score, score_breakdown, critique_failed)
    elif not recommendations:
        # Zero recommendations on a non-final attempt locks it as complete immediately (same as
        # rejecting every recommendation), so it needs the same "score it now" trigger.
        task_score, score_breakdown, critique_failed = await _score_task_report(event_type, file.filename, file_bytes, file.content_type)
        await set_task_score(report_id, task_score, score_breakdown, critique_failed)

    sections = await _build_sections(deviation_id, docx_bytes)
    return _build_section_response(_find_task(sections, task_index))


@router.post(
    "/{record_id}/sections/{task_index}/recommendations/{recommendation_id}/decision",
    response_model=TaskCritiqueSection,
)
async def decide_recommendation(
    record_id: str, task_index: int, recommendation_id: int, request: RecommendationDecisionRequest
) -> TaskCritiqueSection:
    if request.decision == "rejected" and not request.reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A reason is required to reject a recommendation")

    deviation_id, _row, event_type = await _deviation_id_and_row(record_id)
    docx_bytes, _file_name = await _get_source_document(deviation_id, record_id)
    if docx_bytes is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No RCI Plan document found for this investigation yet")

    sections = await _build_sections(deviation_id, docx_bytes)
    section = _find_task(sections, task_index)

    state = compute_section_state(section["report"])
    if state["locked"] or state["latest"] is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This task is locked and no longer accepts decisions")

    recommendation_ids = {r["id"] for r in state["latest"]["recommendations"]}
    if recommendation_id not in recommendation_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such recommendation on this task's current report")

    await set_recommendation_decision(deviation_id, task_index, recommendation_id, request.decision, request.reason)

    sections = await _build_sections(deviation_id, docx_bytes)
    section = _find_task(sections, task_index)
    new_state = compute_section_state(section["report"])
    if new_state["status"] == "complete" and new_state["latest"]["task_score"] is None:
        # Rejecting every recommendation just locked this report immediately — score it now.
        file_bytes = await fetch_report_file_bytes(new_state["latest"]["id"])
        if file_bytes is not None:
            task_score, score_breakdown, critique_failed = await _score_task_report(event_type, new_state["latest"]["file_name"], file_bytes, None)
            await set_task_score(new_state["latest"]["id"], task_score, score_breakdown, critique_failed)
            sections = await _build_sections(deviation_id, docx_bytes)
            section = _find_task(sections, task_index)

    return _build_section_response(section)


@router.get(
    "/{record_id}/sections/{task_index}/history",
    response_model=List[RecommendationHistoryAttempt],
)
async def get_recommendation_history(record_id: str, task_index: int) -> List[RecommendationHistoryAttempt]:
    """Full audit trail across every attempt; the main reports table only ever keeps the current attempt (replaced in place each upload), so this append-only log is the only place prior attempts survive."""
    deviation_id, _row, _event_type = await _deviation_id_and_row(record_id)
    history = await fetch_recommendation_history(deviation_id, task_index)
    return [RecommendationHistoryAttempt(**attempt) for attempt in history]