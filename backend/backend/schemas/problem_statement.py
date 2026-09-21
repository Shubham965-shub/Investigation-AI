"""Schemas for problem statement generation (proxies DS POST /ps/v2/generate)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# DS v2 endpoint does not support "OOS/OOT" as a combined type.
PSEventType = Literal["Deviation", "OOS", "OOT", "Market Complaint"]


class ProblemStatementGenerateRequest(BaseModel):
    event_type: PSEventType
    trackwise_fields: Dict[str, Any] = Field(
        ..., description="Trackwise fields for the event type"
    )


class ProblemStatementGenerateResponse(BaseModel):
    event_type: str
    problem_statement: str


class ProblemStatementUpdateRequest(BaseModel):
    """Manual edit to an already-generated problem statement, now persisted (previously session-only, lost on refresh)."""

    problem_statement: str


class SimilarInvestigation(BaseModel):
    """A historic investigation this one is similar to, ranked by cosine similarity over ds's precomputed embeddings."""

    deviation_id: int
    title: str
    status: Literal["Open", "Closed", "Cancelled", "Unknown"]
    relevance_score: float


class ProblemStatementEnhancement(BaseModel):
    """One concrete, real difference between the raw TrackWise text and the generated problem statement (see ds's identically-shaped schema)."""

    category: str
    tw_excerpt: str
    llm_excerpt: str


class ProblemStatementEnhancementsResponse(BaseModel):
    enhancements: List[ProblemStatementEnhancement] = Field(default_factory=list)


class ProblemStatementRecord(BaseModel):
    """Investigation record hydrated from the STAR schema; problem_statement is None until generated, editable while locked_for_editing is False."""

    record_id: str
    event_type: PSEventType
    trackwise_fields: Dict[str, Any]
    problem_statement: Optional[str] = None
    # Verbatim dim_event.criticality; only meaningful for Deviation/Market Complaint, used to pick the Stepper's SLA tier.
    criticality: Optional[str] = None
    # dim_event.event_classification — additive, not a replacement for criticality (stays binary). "Critical"/"Major"/"Minor" or None (OOS/OOT, unclassified, or N/A Complaint).
    event_classification: Optional[str] = None
    # How many modules Trackwise's status implies are already done — lets the frontend show this module complete even without a generated problem_statement.
    stage: int = 0
    # True once Evidence Collection has real data — same "stop editing upstream once downstream work begins" rule as RCI Plan's locked_for_editing.
    locked_for_editing: bool = False
    # None = never generated yet (frontend shows a "Generate" affordance); [] = generated, nothing meaningful found.
    enhancements: Optional[List[ProblemStatementEnhancement]] = None
