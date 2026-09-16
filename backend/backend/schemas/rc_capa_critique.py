"""Schemas for RC & CAPA Critique (module step 6): one shared upload cycle per investigation, critiqued into rc_impact/capa categories by ds."""
from __future__ import annotations

import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from backend.schemas.scoring import ScoreBreakdownTable


class RcCapaRecommendation(BaseModel):
    id: int
    description: str
    # Only set for rc_impact recommendations — tags rc vs impact so the frontend can render two labeled subsections. None for capa, or legacy rows.
    type: Optional[Literal["rc", "impact"]] = None
    decision: Literal["pending", "accepted", "rejected"] = "pending"
    reason: Optional[str] = None


class RcCapaCritique(BaseModel):
    category: Literal["rc_impact", "capa"]
    # Condensed by ds from the report's own extracted section text (no LLM parsing) — condensation only, never adds new facts.
    summary: Optional[str] = None
    recommendations: List[RcCapaRecommendation] = []


class RcCapaReport(BaseModel):
    id: int
    attempt_number: int
    file_name: str
    is_gospel: bool
    # ds-generated percentages, set once the report becomes final (gospel or 3rd attempt). rc/impact are separate rubric sections; capa is CAPA alone.
    rc_score: Optional[int] = None
    impact_score: Optional[int] = None
    capa_score: Optional[int] = None
    # rc_score's and capa_score's raw marks combined over their combined max — not a naive average of the two percentages.
    total_score: Optional[int] = None
    # Full per-checkpoint breakdown (rc + impact + capa sections all present).
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
    # None until "Accept and Push for SIT Lead Review"; no real external SIT integration yet, so only ever reaches 'pending'.
    sit_review_status: Optional[Literal["pending"]] = None
    # Investigation-level fields for the completion screen's info badges.
    investigator: Optional[str] = None
    due_date: Optional[str] = None


class RecommendationDecisionRequest(BaseModel):
    decision: Literal["accepted", "rejected"]
    reason: Optional[str] = None