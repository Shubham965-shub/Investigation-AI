"""Schemas shared across trackwise-fields-driven modules; trackwise_fields is a loose dict since DS owns field validation (its 422s pass through as-is)."""
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
