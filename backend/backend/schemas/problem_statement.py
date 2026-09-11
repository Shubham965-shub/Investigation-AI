"""Schemas for problem statement generation (proxies DS POST /ps/v2/generate)."""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

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
    """Manual edit to an already-generated problem statement (2026-09-10, per
    the user) — previously session-only (see ProblemStatementRecord's own
    docstring: "read-only for now"), lost on refresh/navigation with no
    backend endpoint to persist it at all."""

    problem_statement: str


class SimilarInvestigation(BaseModel):
    """A historic investigation this one is based on/similar to, ranked by
    cosine similarity over ds's precomputed description embeddings
    (t_deviations_vector_test)."""

    deviation_id: int
    title: str
    status: Literal["Open", "Closed", "Cancelled", "Unknown"]
    relevance_score: float


class ProblemStatementRecord(BaseModel):
    """A real investigation record's Trackwise fields, hydrated from the STAR
    schema. problem_statement is None until one has been generated and
    persisted to investigation_problem_statements (generated_content.sql) —
    editable via PUT /problem-statement/{record_id} (2026-09-10, per the
    user) as long as locked_for_editing is False."""

    record_id: str
    event_type: PSEventType
    trackwise_fields: Dict[str, Any]
    problem_statement: Optional[str] = None
    # Verbatim dim_event.criticality (upstream/Trackwise, same source Action
    # Center reads) — None when Trackwise hasn't set it. Only meaningful for
    # Deviation/Market Complaint; OOS/OOT don't carry a criticality tier here
    # (2026-08-26, per the user: used to pick which SLA tier the Stepper
    # shows for this specific investigation).
    criticality: Optional[str] = None
    # dim_event.event_classification (2026-09-11, per the data engineer) — a
    # separate, additive field, NOT a replacement for criticality above
    # (which stays binary "Critical"/"Non-Critical" and is unaffected).
    # Values: "Critical"/"Major"/"Minor" for Deviation/Complaint records, or
    # None for an OOS/OOT record (no Major/Minor concept exists for those
    # types), a Deviation/Complaint with no classification set yet, or a
    # Complaint marked "Not Applicable" (deliberately collapsed to None
    # upstream). Render "Critical" with the same tag/styling already used
    # for Critical elsewhere; "Major"/"Minor" get their own (new) tag; None
    # gets no tag at all, same as today.
    event_classification: Optional[str] = None
    # How many modules Trackwise's own status implies are already done (see
    # src/db/module_stage.py) — lets the frontend show this module as
    # already-complete (read-only trackwise fields) even without a real
    # generated problem_statement, when stage >= 1.
    stage: int = 0
    # True once Evidence Collection (the next step) has any real data — same
    # "downstream work has begun, stop editing upstream" rule RCI Plan's own
    # locked_for_editing already uses, one step earlier in the wizard
    # (2026-08-21, per the user).
    locked_for_editing: bool = False
