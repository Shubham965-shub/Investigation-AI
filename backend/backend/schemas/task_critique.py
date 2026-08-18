"""Schemas for Task Critique (module step 5) — each task is one block
extracted from the RCI Plan document (services/rci_plan_extraction.py) and
critiqued as a unit via an uploaded report. See db/task_critique_queries.py's
compute_section_state for the upload/lock/status business rules these shapes
carry the result of."""
from __future__ import annotations

import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from backend.schemas.scoring import ScoreBreakdownTable


class TaskCritiqueRecommendation(BaseModel):
    id: int
    description: str
    decision: Literal["pending", "accepted", "rejected"] = "pending"
    reason: Optional[str] = None


class TaskCritiqueReport(BaseModel):
    id: int
    attempt_number: int
    file_name: str
    is_gospel: bool
    # DS-generated (/critique/analyse-task-report) — task_score stays None
    # until DS returns one (or permanently, for an is_gospel report, which is
    # never critiqued at all).
    summary: Optional[str] = None
    task_score: Optional[int] = None
    # Full per-checkpoint breakdown, set alongside task_score — see
    # schemas/scoring.py.
    score_breakdown: List[ScoreBreakdownTable] = []
    # True when ds's critique came back degenerate (no real tasks found to
    # review) — see generated_content.sql's table comment. Only ever true for
    # reports uploaded before the pre-upload format/degenerate-result checks
    # existed; new uploads that would trigger this are rejected outright.
    critique_failed: bool = False
    uploaded_at: datetime.datetime
    recommendations: List[TaskCritiqueRecommendation] = []


class TaskCritiqueSection(BaseModel):
    # 0-based position within the extracted task list — not a DB foreign
    # key (see generated_content.sql's table comment on why).
    task_index: int
    title: str
    correlation: Optional[str] = None
    task_count: int
    due_date: Optional[str] = None
    assignee: Optional[str] = None
    status: Literal["pending", "in_progress", "complete"]
    upload_count: int
    max_uploads: int = 3
    locked: bool
    # True only right after a report's recommendations were ALL rejected —
    # the next upload is taken as the final "gospel" report, no critique run.
    next_upload_is_final: bool = False
    can_upload: bool
    latest_report: Optional[TaskCritiqueReport] = None


class TaskCritiqueListResponse(BaseModel):
    record_id: str
    sections: List[TaskCritiqueSection]
    # False when neither module 4's export nor a manually-uploaded stand-in
    # exists yet — the frontend shows an upload prompt instead of the list.
    has_source_document: bool = False
    source_document_name: Optional[str] = None


class RecommendationDecisionRequest(BaseModel):
    decision: Literal["accepted", "rejected"]
    reason: Optional[str] = None


class RecommendationHistoryAttempt(BaseModel):
    """One past attempt's audit-log entry — see
    investigation_task_critique_recommendation_history. Same rich
    {id, description, decision, reason} shape as the live report's
    recommendations (2026-08-18, per the user: accept/reject/reason needs to
    survive here too) — set_recommendation_decision keeps this row's copy in
    sync as decisions are made, independent of the current report/lock state
    (stays visible even once the task is scored and complete)."""

    attempt_number: int
    summary: Optional[str] = None
    recommendations: List[TaskCritiqueRecommendation] = []
    created_at: datetime.datetime