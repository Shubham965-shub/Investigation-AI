"""
V2 Schemas for structured problem statement generation.
Input based on trackwise field requirements and event types.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Literal, Dict, Any

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


class ProblemStatementEnhancement(BaseModel):
    """One concrete, real difference between the raw TrackWise text and the generated problem statement."""
    category: str = Field(..., description='Short label for the kind of change, e.g. "Typo", "Date Format", "Length & Clarity", "Raw Data", "Root Cause & Outcome" — or another short label if none of those fit.')
    tw_excerpt: str = Field(..., description="Excerpt/description of the relevant raw TrackWise text")
    llm_excerpt: str = Field(..., description="What it became in the generated problem statement")


class ProblemStatementEnhancementsRequest(BaseModel):
    """Request for a categorized diff between the raw TrackWise description and the generated problem statement."""
    raw_description: str = Field(..., description="The raw TrackWise description text the problem statement was generated from")
    problem_statement: str = Field(..., description="The generated problem statement")


class ProblemStatementEnhancementsResponse(BaseModel):
    """Categorized diff, empty when the two texts are effectively equivalent — never fabricated."""
    enhancements: List[ProblemStatementEnhancement] = Field(default_factory=list)