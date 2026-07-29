"""Schemas for evidence collection (proxies DS POST /evidence/collect)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from backend.schemas.common import ArchetypeInfo, EventType, TrackwiseRequest


class EvidenceCollectionRequest(TrackwiseRequest):
    pass


class EvidenceItem(BaseModel):
    description: str
    is_new: bool = False
    is_checked: bool = True


class EvidenceCollectionResponse(BaseModel):
    event_type: str
    failure_type: str
    archetype: ArchetypeInfo
    evidence: List[EvidenceItem]
    total_evidence_count: int


class EvidenceCollectionRecord(BaseModel):
    """A real investigation record's Trackwise fields, hydrated from the STAR
    schema. evidence is None until a list has been generated and persisted to
    investigation_evidence_items (generated_content.sql); read-only for now."""

    record_id: str
    event_type: EventType
    trackwise_fields: Dict[str, Any]
    evidence: Optional[List[EvidenceItem]] = None
    # See src/schemas/problem_statement.py's stage field for what this means.
    stage: int = 0
