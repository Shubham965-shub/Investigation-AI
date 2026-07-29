"""
V2 Schemas for structured problem statement generation.
Input based on trackwise field requirements and event types.
"""

from pydantic import BaseModel, Field, validator
from typing import Literal, Dict, Any

from src.agents.shared.schemas import validate_trackwise_fields


class ProblemStatementGenerationRequest(BaseModel):
    """Request to generate structured problem statement."""
    event_type: Literal["Deviation", "OOS", "OOT", "Market Complaint"]
    trackwise_fields: Dict[str, Any] = Field(
        ...,
        description="Dictionary of trackwise fields based on event type"
    )

    @validator("trackwise_fields", pre=True)
    def _validate_trackwise_fields(cls, v, values):
        return validate_trackwise_fields(values.get("event_type", ""), v, by_alias=True)


class ProblemStatementGenerationResponse(BaseModel):
    """Response with generated problem statement."""
    event_type: str = Field(..., description="Type of event")
    problem_statement: str = Field(
        ...,
        description="Generated structured problem statement"
    )