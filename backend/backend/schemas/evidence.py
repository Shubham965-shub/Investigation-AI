"""Schemas for evidence collection (proxies DS POST /evidence/collect)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from backend.schemas.common import ArchetypeInfo, EventType, TrackwiseRequest


class EvidenceCollectionRequest(TrackwiseRequest):
    # Groundwork only — carried through to DS via model_dump(), no matching logic attached yet.
    rci_id: Optional[str] = None


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
    """Investigation record hydrated from the STAR schema; evidence is None until generated. Read-only for now."""

    record_id: str
    event_type: EventType
    trackwise_fields: Dict[str, Any]
    evidence: Optional[List[EvidenceItem]] = None
    # See src/schemas/problem_statement.py's stage field for what this means.
    stage: int = 0
