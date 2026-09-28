"""
Schemas for the evidence collection API.
Trackwise field models and ArchetypeInfo live in src.agents.shared.schemas.
"""

from pydantic import BaseModel, Field, validator
from typing import Any, Dict, List, Literal, Optional

from src.agents.shared.schemas import (
    ArchetypeInfo,
    DeviationTrackwiseFields,
    MarketComplaintTrackwiseFields,
    OOSTrackwiseFields,
    validate_trackwise_fields,
)

# Re-export so existing imports of these from this module still work.
__all__ = [
    "DeviationTrackwiseFields",
    "OOSTrackwiseFields",
    "MarketComplaintTrackwiseFields",
    "ArchetypeInfo",
    "EvidenceCollectionRequest",
    "EvidenceItem",
    "EvidenceCollectionResponse",
]


class EvidenceCollectionRequest(BaseModel):
    """Request to collect evidence for a quality event."""
    event_type: Literal["Deviation", "OOS", "OOT", "OOS/OOT", "Market Complaint"]
    trackwise_fields: Dict[str, Any] = Field(
        ..., description="Trackwise fields for the event type"
    )
    rci_id: Optional[str] = Field(
        default=None, description="Optional RCI identifier for events with multiple concurrent RCIs"
    )

    @validator("trackwise_fields", pre=True)
    def _validate_trackwise_fields(cls, v, values):
        return validate_trackwise_fields(values.get("event_type", ""), v)


class EvidenceItem(BaseModel):
    description: str
    is_new: bool = False


class EvidenceCollectionResponse(BaseModel):
    event_type: str
    failure_type: str
    archetype: ArchetypeInfo
    evidence: List[EvidenceItem]
    total_evidence_count: int
