from pydantic import BaseModel, Field, validator
from typing import Any, Dict, List, Literal, Optional

from src.agents.shared.schemas import (
    ArchetypeInfo,
    validate_trackwise_fields,
)

class RciPlanRequest(BaseModel):
    """Request to generate an RCI plan for a quality event."""
    event_type: Literal["Deviation", "OOS", "OOT", "OOS/OOT", "Market Complaint"]
    trackwise_fields: Dict[str, Any] = Field(
        ..., description="Trackwise fields for the event type"
    )

    @validator("trackwise_fields", pre=True)
    def _validate_trackwise_fields(cls, v, values):
        return validate_trackwise_fields(
            event_type=values.get("event_type", ""), 
            event_functionality="rci_plan", 
            v=v
        )


class RciTaskItem(BaseModel):
    description: str


class RciSectionItem(BaseModel):
    title: str
    correlation: Optional[str] = None
    six_m_bucket: Optional[str] = None
    tasks: List[RciTaskItem]


class RciPlanResponse(BaseModel):
    event_type: str
    failure_type: str
    archetype: ArchetypeInfo
    sections: List[RciSectionItem]
    total_sections_count: int
    total_tasks_count: int


class ExcelUploadResponse(BaseModel):
    status: str
    message: str
    archetypes_processed: List[str]
    plans_created: int
    sections_created: int
    tasks_created: int
