from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, status

from backend.clients.ds_client import _raise_for_upstream_error, get_client
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

# Mirrors ds's UNADDRESSED_MARKER (ds/src/agents/critique/graph/nodes.py) so carried-forward
# recommendations still sort first after this route re-flattens per-sub-task lists.
_UNADDRESSED_MARKER = "Still unaddressed from the previous review."
_MAX_RECOMMENDATIONS = 5

router = APIRouter(prefix="/task-critique", tags=["Task Critique"])


async def _get_source_document(deviation_id: int, record_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """A manually uploaded / externally-fed document (e.g. a future TrackWise
    pipeline) is always preferred when it exists; module 4's own export is
    only ever the fallback (per the user, 2026-08-06)."""
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
    """Scores the final (locked) report against DS's rubric-based /score/report
    endpoint (out of 40 for task_report_execution) and returns
    (percentage rounded for task_score, the full `info` breakdown table list —
    see schemas/scoring.py — for score_breakdown, critique_failed). Best-effort
    — a scoring failure must not undo an upload that already succeeded and
    persisted, but it must be flagged (critique_failed=True) rather than
    silently indistinguishable from "not scored yet" (ticket 500954: tasks
    were reaching "complete" with a NULL score and no record of why)."""
    client = get_client()
    try:
        response = await client.post(
            "/score/report",
            data={"event_type": event_type},
            files={"file": (filename, file_bytes, content_type)},
        )
        response.raise_for_status()
        data = response.json()
        task_report_execution = data.get("task_report_execution")
    except httpx.HTTPError:
        logger.warning("Task report scoring failed for %s", filename, exc_info=True)
        return None, [], True
    except (ValueError, KeyError, TypeError):
        # Malformed 200 response (bad JSON, unexpected shape) — treat the
        # same as a scoring failure rather than letting it raise unhandled.
        logger.warning("Task report scoring returned a malformed response for %s", filename, exc_info=True)
        return None, [], True
    info = data.get("info") or []
    if not task_report_execution:
        # DS responded successfully but didn't detect a Task Report section in
        # this document (e.g. only an RC/Impact/CAPA section was found) — this
        # is a 200, not an httpx.HTTPError, so it must be flagged here too.
        logger.warning("No task_report_execution section detected for %s — scoring incomplete", filename)
        return None, info, True
    return round(task_report_execution["percentage"]), info, False


def _find_task(sections: List[Dict[str, Any]], task_index: int) -> Dict[str, Any]:
    for section in sections:
        if section["task_index"] == task_index:
            return section
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_TASK_NOT_FOUND_DETAIL)


def _describe_task(section: Dict[str, Any]) -> str:
    """Describes what this specific RCI-plan task/section is investigating (e.g.
    "Analyst Verification", "Instrument Calibration Check") so DS can check the
    uploaded report actually addresses this task, not just the overall investigation."""
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
    """Manual/externally-fed upload — takes priority over module 4's own
    export once present (see _get_source_document); replaces any prior
    upload for this investigation (UNIQUE(deviation_id) + upsert)."""
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
async def upload_task_report(record_id: str, task_index: int, file: UploadFile) -> TaskCritiqueSection:
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
        # Rejected outright — no attempt consumed, no critique call (per the
        # user, 2026-08-12). Real completed reports never literally say "Title
        # of the task" (that's a blank-template-only label), so it's excluded
        # from the required markers — see task_report_format.py.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This document doesn't match the required task report format — please upload the correct report.",
        )

    if is_gospel:
        report_id = await upsert_report(deviation_id, task_index, attempt_number, file.filename or "report", file_bytes, is_gospel=True)
        # A gospel report is final the moment it's uploaded — no critique, no
        # further review possible (per the user, 2026-08-07: score whichever
        # report ends up being the task's final one, gospel or 3rd attempt).
        task_score, score_breakdown, critique_failed = await _score_task_report(event_type, file.filename, file_bytes, file.content_type)
        await set_task_score(report_id, task_score, score_breakdown, critique_failed)
        sections = await _build_sections(deviation_id, docx_bytes)
        return _build_section_response(_find_task(sections, task_index))

    # Real, genuinely per-task DS endpoint (ds/src/agents/critique/api/routes/
    # task_report_critique_route.py) — 7-dimension critique with vision
    # analysis on embedded photos. This path used to be shadowed by
    # critique_route.py's combined RC+CAPA endpoint registering the identical
    # path (both /critique/analyse-task-report, first-registered-wins routing)
    # — fixed 2026-08-06 by moving that one to its own path,
    # /critique/critique-rc-conclusion-and-capa (see routers/rc_capa_critique.py,
    # which already used the two even-more-specific split endpoints and so was
    # never affected by this collision). That combined endpoint was never
    # actually called by any module and was removed entirely on 2026-08-20.
    # Called BEFORE persisting anything, so a transient DS failure doesn't
    # burn one of the 3 real upload attempts.
    # problem_statement + task_description let DS reject an irrelevant/mismatched
    # upload with a 422 before running any critique LLM calls — task_description
    # catches the narrower case of the right investigation's report being uploaded
    # to the wrong task/section (see ds's relevance_validation.py).
    # deviation_id + task_index (2026-08-14, per the user) let DS look up this
    # task's previous attempt and check whether its accepted-but-still-pending
    # recommendations are actually addressed by this upload, regenerating any
    # that aren't (see ds/src/agents/critique/GAPS.md). Sent as form fields, not
    # query params like the three above — DS declares them via Form(...), not as
    # plain scalars, since they arrive alongside the multipart file upload.
    problem_statement = await fetch_problem_statement(deviation_id) or row["description"] or row["title"]
    task_description = _describe_task(section)

    # Scoring only needs the raw report bytes, not the critique response, so it's
    # started here and run concurrently with the critique call below rather than
    # after it — cuts the final upload's latency from critique_time + scoring_time
    # down to max(critique_time, scoring_time).
    score_task: Optional["asyncio.Task[Tuple[Optional[int], List[Dict[str, Any]], bool]]"] = None
    if attempt_number >= MAX_UPLOADS:
        score_task = asyncio.create_task(
            _score_task_report(event_type, file.filename, file_bytes, file.content_type)
        )

    client = get_client()
    try:
        response = await client.post(
            "/critique/analyse-task-report",
            params={
                "problem_statement": problem_statement,
                "event_type": event_type,
                "task_description": task_description,
            },
            data={
                "deviation_id": str(deviation_id),
                "task_index": str(task_index),
            },
            files={"file": (file.filename, file_bytes, file.content_type)},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if score_task is not None:
            score_task.cancel()
        _raise_for_upstream_error(exc)
    except httpx.RequestError as exc:
        if score_task is not None:
            score_task.cancel()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"InvestigationAi_DS service unreachable: {exc}",
        ) from exc

    data = response.json()
    # TaskReportCritiqueResponse (v8): {problem_statement, objective,
    # task_critiques: [{task_number, title, recommendations: [str], strengths}],
    # overall_report_summary, total_tasks_analyzed} — dimensions are internal-only
    # on the DS side now; recommendations is already a flat, ready-to-show list.
    if data.get("total_tasks_analyzed", 0) == 0:
        # ds found no real tasks to critique at all — the local format check
        # (task_report_format.py) already blocks most wrong documents, but a
        # file can pass that (has the right section labels present somewhere)
        # and still not be a genuine, parseable task report. Same "reject
        # outright" rule (2026-08-13, per the user): no attempt consumed, no
        # persistence — this is the deeper check for cases the local one
        # can't catch (e.g. the format check alone can't parse actual task
        # content the way ds's own extraction does).
        if score_task is not None:
            score_task.cancel()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This document doesn't match the required task report format — please upload the correct report.",
        )

    # A single uploaded report can cover several checklist items in this section (one
    # "Inference:" block per item), so ds returns one task_critiques entry per block —
    # each already capped at 5 recommendations on its own. Flattening them here can still
    # exceed 5 combined, so re-cap after flattening, keeping still-unaddressed
    # carried-forward items first.
    # The displayed "Summary Of the Report" is positive-only (what's working well), built
    # from every task's `strengths` — gaps are already surfaced separately via
    # `recommendations`, so DS no longer generates a gap-focused summary at all.
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

    report_id = await upsert_report(deviation_id, task_index, attempt_number, file.filename or "report", file_bytes, is_gospel=False)
    await save_critique(report_id, summary, task_score=None, recommendations=recommendations)
    await insert_recommendation_history(deviation_id, task_index, attempt_number, summary, recommendations)

    # The 3rd attempt is final regardless of how its recommendations end up
    # decided (see critique_state.compute_upload_state) — score it now, since
    # no further upload will ever supersede it. The scoring call was already
    # kicked off above, concurrently with the critique call, so this just
    # awaits its (by now likely-finished) result.
    if score_task is not None:
        task_score, score_breakdown, critique_failed = await score_task
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
        # Rejecting every recommendation just locked this report immediately
        # (see critique_state.compute_upload_state) rather than waiting on a
        # further gospel upload — score it now, the same trigger a gospel/
        # 3rd-attempt upload already gets (2026-08-14, per the user).
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
    """The full audit trail across every attempt for this task — independent
    of lock/complete state, so it stays visible even once the task is scored
    and done (2026-08-18, per the user). Task Critique only ever keeps the
    CURRENT attempt on investigation_task_critique_reports (replaced in
    place each upload), so this separate append-only log is the only place
    a prior attempt's recommendations survive being superseded."""
    deviation_id, _row, _event_type = await _deviation_id_and_row(record_id)
    history = await fetch_recommendation_history(deviation_id, task_index)
    return [RecommendationHistoryAttempt(**attempt) for attempt in history]