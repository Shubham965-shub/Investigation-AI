"""
Schemas for the interview questionnaire API.
Trackwise field models and ArchetypeInfo live in src.agents.shared.schemas.
"""

from pydantic import BaseModel, Field, validator
from typing import Any, Dict, List, Literal, Optional

from src.agents.shared.schemas import ArchetypeInfo, validate_trackwise_fields

__all__ = [
    "QuestionCollectionRequest",
    "InterviewQuestion",
    "QuestionCollectionResponse",
]


class QuestionCollectionRequest(BaseModel):
    """Request to generate interview questions for a quality event."""
    event_type: Literal["Deviation", "OOS", "OOT", "OOS/OOT", "Market Complaint"]
    trackwise_fields: Dict[str, Any] = Field(
        ..., description="Trackwise fields for the event type"
    )

    @validator("trackwise_fields", pre=True)
    def _validate_trackwise_fields(cls, v, values):
        return validate_trackwise_fields(values.get("event_type", ""), v)


class InterviewQuestion(BaseModel):
    description: str
    is_new: bool = False


class QuestionCollectionResponse(BaseModel):
    event_type: str
    failure_type: str
    archetype: ArchetypeInfo
    questions: List[InterviewQuestion]
    total_questions_count: int
