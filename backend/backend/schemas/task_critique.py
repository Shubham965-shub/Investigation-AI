"""Schemas for Task Critique (module step 5) — each task is one block
extracted from the RCI Plan document (services/rci_plan_extraction.py) and
critiqued as a unit via an uploaded report. See db/task_critique_queries.py's
compute_section_state for the upload/lock/status business rules these shapes
carry the result of."""
from __future__ import annotations

import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


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