"""Schemas shared across the trackwise-fields-driven modules.

Mirrors backend.agents.shared.schemas in InvestigationAi_DS: event_type is the
same literal there, and trackwise_fields is deliberately kept as a loose
dict here — the DS service is the source of truth for per-event-type field
validation, and its 422 responses are forwarded to the frontend as-is.
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel

EventType = Literal["Deviation", "OOS", "OOT", "OOS/OOT", "Market Complaint"]


class TrackwiseRequest(BaseModel):
    """Base request shape shared by evidence, questionnaire, RCI plan and PS generation."""

    event_type: EventType
    trackwise_fields: Dict[str, Any]


class ArchetypeInfo(BaseModel):
    id: Optional[int] = None
    name: str
    is_new: bool
    confidence_score: Optional[float] = None
    reasoning: Optional[str] = None
