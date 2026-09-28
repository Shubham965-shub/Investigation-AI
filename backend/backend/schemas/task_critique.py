"""Schemas for Task Critique (module step 5): each task is one block extracted from the RCI Plan document, critiqued as a unit via an uploaded report."""
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
    # task_score stays None until DS returns one, or permanently for an is_gospel report (never critiqued).
    summary: Optional[str] = None
    task_score: Optional[int] = None
    # Full per-checkpoint breakdown, set alongside task_score.
    score_breakdown: List[ScoreBreakdownTable] = []
    # True when ds's critique came back degenerate (no real tasks found) — surfaced via
    # critique_failed rather than a permanent rejection now, since that outcome can only be
    # discovered after the upload is already persisted (see critique_pending below).
    critique_failed: bool = False
    # True while DS's critique/scoring calls are still running in the background — see
    # TaskCritiqueSection.status's "processing" value, which this mirrors at the report level.
    critique_pending: bool = False
    uploaded_at: datetime.datetime
    recommendations: List[TaskCritiqueRecommendation] = []


class TaskCritiqueSection(BaseModel):
    # 0-based position within the extracted task list — not a DB foreign key.
    task_index: int
    title: str
    correlation: Optional[str] = None
    task_count: int
    due_date: Optional[str] = None
    assignee: Optional[str] = None
    # "processing": upload persisted, DS critique/scoring still running in the background.
    status: Literal["pending", "processing", "in_progress", "complete"]
    upload_count: int
    max_uploads: int = 3
    locked: bool
    # True only right after a report's recommendations were ALL rejected — next upload is taken as the final "gospel" report.
    next_upload_is_final: bool = False
    can_upload: bool
    latest_report: Optional[TaskCritiqueReport] = None


class TaskCritiqueListResponse(BaseModel):
    record_id: str
    sections: List[TaskCritiqueSection]
    # False when no source document exists yet — frontend shows an upload prompt instead of the list.
    has_source_document: bool = False
    source_document_name: Optional[str] = None


class RecommendationDecisionRequest(BaseModel):
    decision: Literal["accepted", "rejected"]
    reason: Optional[str] = None


class RecommendationHistoryAttempt(BaseModel):
    """One past attempt's audit-log entry; stays in sync with accept/reject decisions and stays visible even after the task is scored and complete."""

    attempt_number: int
    summary: Optional[str] = None
    recommendations: List[TaskCritiqueRecommendation] = []
    created_at: datetime.datetime