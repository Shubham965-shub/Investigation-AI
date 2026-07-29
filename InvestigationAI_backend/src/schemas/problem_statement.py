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


class ProblemStatementRecord(BaseModel):
    """A real investigation record's Trackwise fields, hydrated from the STAR
    schema. problem_statement is None until one has been generated and
    persisted to investigation_problem_statements (generated_content.sql);
    read-only for now."""

    record_id: str
    event_type: PSEventType
    trackwise_fields: Dict[str, Any]
    problem_statement: Optional[str] = None
    # How many modules Trackwise's own status implies are already done (see
    # src/db/module_stage.py) — lets the frontend show this module as
    # already-complete (read-only trackwise fields) even without a real
    # generated problem_statement, when stage >= 1.
    stage: int = 0
