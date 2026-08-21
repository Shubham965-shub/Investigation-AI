"""Schemas for RC & CAPA Critique (module step 6) — one shared upload cycle
per investigation, critiqued into two fixed categories (rc_impact/capa) by
ds's POST /critique/analyse-task-report. See db/critique_state.py's
compute_upload_state for the upload/lock/status business rules these shapes
carry the result of — identical rule to Task Critique, shared not duplicated.
"""
from __future__ import annotations

import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from backend.schemas.scoring import ScoreBreakdownTable


class RcCapaRecommendation(BaseModel):
    id: int
    description: str
    decision: Literal["pending", "accepted", "rejected"] = "pending"
    reason: Optional[str] = None


class RcCapaCritique(BaseModel):
    category: Literal["rc_impact", "capa"]
    # The report's own RC Conclusion / CAPA section text, pulled by ds via plain docx
    # parsing (extract_rci_report_sections) — never LLM-generated (2026-08-20, per the
    # user). No separate LLM "strengths" verdict is generated or shown here anymore.
    summary: Optional[str] = None
    recommendations: List[RcCapaRecommendation] = []


class RcCapaReport(BaseModel):
    id: int
    attempt_number: int
    file_name: str
    is_gospel: bool
    # ds-generated (/score/report), as percentages — set once this report
    # becomes final (gospel or 3rd attempt); None until then. rc_score
    # combines the Root Cause + Impact sections; capa_score is CAPA alone.
    rc_score: Optional[int] = None
    capa_score: Optional[int] = None
    # Consolidated figure: rc_score's and capa_score's underlying raw marks
    # added together, divided by their combined max — not a naive average of
    # the two percentages.
    total_score: Optional[int] = None
    # Full per-checkpoint breakdown (rc + impact + capa sections all present
    # here) — see schemas/scoring.py.
    score_breakdown: List[ScoreBreakdownTable] = []
    uploaded_at: datetime.datetime
    critiques: List[RcCapaCritique] = []


class RcCapaState(BaseModel):
    record_id: str
    status: Literal["pending", "in_progress", "complete"]
    upload_count: int
    max_uploads: int = 3
    locked: bool
    next_upload_is_final: bool = False
    can_upload: bool
    latest_report: Optional[RcCapaReport] = None
    # None until "Accept and Push for SIT Review" has been used — no real
    # external SIT review integration yet, so this only ever reaches
    # 'pending' for now (see db/schema.sql's investigation_rc_capa_sit_reviews).
    sit_review_status: Optional[Literal["pending"]] = None
    # Investigation-level fields (not per-report) for the completion screen's
    # info badges — sourced from db/queries.py's fetch_investigation_row,
    # same real dim_investigator/fact_qms_event.due_date columns Action
    # Center already surfaces.
    investigator: Optional[str] = None
    due_date: Optional[str] = None


class RecommendationDecisionRequest(BaseModel):
    decision: Literal["accepted", "rejected"]
    reason: Optional[str] = None