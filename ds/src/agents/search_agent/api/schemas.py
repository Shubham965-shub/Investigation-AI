"""Pydantic models for the search API request / response."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional, TypeVar, List, Generic

from pydantic import BaseModel, Field, ConfigDict


# ── Enums ───────────────────────────────────────────────────


class DateRangeOption(str, Enum):
    """Predefined date range options."""
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"
    LAST_6_MONTHS = "last_6_months"
    LAST_YEAR = "last_year"
    LAST_18_MONTHS = "last_18_months"
    LAST_2_YEARS = "last_2_years"
    LAST_3_YEARS = "last_3_years"
    ALL = "all"
    CUSTOM = "custom"


class SearchTypeOption(str, Enum):
    """Search type options."""
    KEYWORD = "Keyword"
    CONTEXTUAL = "Contextual"
    HYBRID = "Hybrid"


class SearchViaOption(str, Enum):
    """Field selection for searching."""
    ROOT_CAUSE = "Root Cause"
    EVENT_DESCRIPTION = "Event Description"
    BOTH = "Both"

#-------------------------------------------------------------------------------------
# Request
#-------------------------------------------------------------------------------------

class SearchRequest(BaseModel):
    """POST body for ``/api/search``."""

    problem_statement: str = Field(..., min_length=1, description="The investigation problem statement to search on (keyword or semantic)")
    
    search_on: Optional[str] = Field(
        None, 
        description="Filter by qe_type column (quality event type)"
    )
    
    search_type: SearchTypeOption = Field(
        default=SearchTypeOption.HYBRID,
        description="Search strategy: Keyword (exact match), Contextual (semantic), or Hybrid (both)"
    )
    
    date_range: DateRangeOption = Field(
        default=DateRangeOption.ALL,
        description="Predefined date range for date_opened column"
    )
    
    custom_date_from: Optional[str] = Field(
        None,
        description="Custom start date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS) if date_range=custom"
    )
    
    custom_date_to: Optional[str] = Field(
        None,
        description="Custom end date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS) if date_range=custom"
    )
    
    sites: list[str] = Field(
        default_factory=lambda: ["all"],
        description='List of site locations (filters on location column). Use ["all"] to skip filter'
    )
    
    instruments: list[str] = Field(
        default_factory=lambda: ["all"],
        description='List of instruments (filters on instrument_equipement_name column). Use ["all"] to skip filter'
    )
    
    materials: list[str] = Field(
        default_factory=lambda: ["all"],
        description='List of materials (filters on name_of_material column). Use ["all"] to skip filter'
    )
    
    search_via: SearchViaOption = Field(
        default=SearchViaOption.BOTH,
        description='Field to search: "Root Cause" (root_cause_summary), "Event Description" (description), or "Both"'
    )

    product_code: list[str] = Field(
        default_factory=lambda: ["all"],
        description='list of product codes (filters on product code column). Use ["all"] to skip filter'
    )
    # product_code: list[str] = Field(
    #     default_factory=lambda: ["all"],
    #     description='List of product codes (filters on product code column). Use ["all"] to skip filter'
    # )
    
    top_k: int = Field(
        default=10,
        ge=1,
        le=5000,
        description="Number of ranked results to return"
    )

    exclude_id: Optional[Any] = Field(
        None,
        description="Deviation ID to exclude from results. Set this to the "
        "current investigation's own ID when searching for similar historical "
        "events using its own problem statement, so the record doesn't match "
        "itself.",
    )

#-------------------------------------------------------------------------------------
# Response 
#-------------------------------------------------------------------------------------

class SearchResultItem(BaseModel):
    """
    A single ranked result with ALL table columns plus search metadata.
    
    All original table columns from the database will be included.
    The following fields are guaranteed to be present from the search:
    """
    class Config:
        extra = "allow"  # Allow additional fields from database columns
    
    # Required fields added by search
    relevance_score: float = Field(..., description="Search relevance score (higher is better)")
    match_type: str = Field(..., description="Type of match: keyword, semantic, or hybrid")
    matched_field: str = Field(..., description="Field that was searched")


class SourceCitation(BaseModel):
    """A source cited in the synthesized answer with all table columns."""
    class Config:
        extra = "allow"  # Allow additional fields from database columns


class LlmData(BaseModel):
    """Dummy internal representation for dashboard."""
    executiveNarrative: str
    topCauseDescription: str
    
    correctiveActionSummary: Optional[str] = None
    preventiveActionSummary: Optional[str] = None

    capaRecurringThemes: list[str]


class SearchResponse(BaseModel):
    """Complete response from ``/api/search``."""

    ranked_results: list[SearchResultItem]
    # synthesized_answer: str
    # source_citations: list[SourceCitation]
    search_metadata: dict[str, Any] = Field(default_factory=dict)
    llmData: LlmData


class RelevanceJudgment(BaseModel):
    """One candidate's relevance verdict from the post-search relevance filter."""
    id: str = Field(..., description="Candidate id, exactly as given in the input")
    relevant: bool = Field(
        ...,
        description="True only if this candidate shares the same underlying failure "
        "mechanism as the current problem statement, not just topical/surface similarity",
    )
    reason: str = Field(..., description="Short phrase explaining the judgment")


class RelevanceFilterResponse(BaseModel):
    """Structured output of the relevance filter LLM call — one judgment per candidate."""
    judgments: list[RelevanceJudgment]


#-------------------------------------------------------------------------------------
# Summary
#-------------------------------------------------------------------------------------

class CumulativeSummaryRequest(BaseModel):
    """POST body for ``/api/cummulative_summary``."""
    deviation_id: list[int] = Field(..., description="List of deviation IDs to summarize")

class CumulativeSummaryItem(BaseModel):
    """A single summarized deviation item."""
    class Config:
        extra = "allow"
    deviation_id: Optional[str] = None
    event_description: Optional[str] = None
    root_cause: Optional[str] = None
    capa: Optional[list[str]] = None
    implementation_date: Optional[str] = None

#-------------------------------------------------------------------------------------
# Root Cause Synthesizer
#-------------------------------------------------------------------------------------

class RCSEvent(BaseModel):
    deviation_id: Any
    description: str
    root_cause_category: str
    root_cause_summary: str
    site: str
    model_config = ConfigDict(populate_by_name=True)

class RootCauseSynthesizerRequest(BaseModel):
    records: list[RCSEvent]
class CAPAEvent(BaseModel):
    deviation_id: Any
    description: str
    root_cause_summary: str
    capa_number: str
    immediate_actions: str
    corrective_actions: str
    preventive_actions: str
    model_config = ConfigDict(populate_by_name=True)

class CAPASynthesizerRequest(BaseModel):
    records: list[CAPAEvent]

class RootCauseSynthSection(BaseModel):
    title: str = Field(
        ...,
        description="Root cause category title (e.g., Machine, Man, Method)"
    )
    items: List[str] = Field(
        ...,
        description="List of deviation summaries formatted as '<deviation_id>: <root_cause_summary>'"
    )
    trend: str = Field(
        ...,
        description="Aggregated analytical trend for the category"
    )

class RootCauseSiteList(BaseModel):
    site: str = Field(
        ...,
        description="Manufacturing site name"
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of deviations across all the sites"
    )
    categories: List[RootCauseSynthSection] = Field(
        ...,
        description="Category-wise root cause synthesis"
    )
class SynthType(str, Enum):
    EVENT = "event"
    CAPA = "capa"
    RC = "rc"


T = TypeVar("T")
class CategoryContainer(BaseModel, Generic[T]):
    category: str = Field(..., description="Category name")
    data: T  # <-- flexible payload

class Site(BaseModel, Generic[T]):
    site: str = Field(..., description="Manufacturing site name")
    total: int = Field(..., ge=0)
    categories: List[CategoryContainer[T]]

class SynthResponse(BaseModel, Generic[T]):
    response: List[Site[T]]   

class RootCauseData(BaseModel):
    trend: str
    items: List[str]  # "<deviation_id>: summary"

class CAPAData(BaseModel):
    trend: str
    corrective_actions: List[str]
    preventive_actions: List[str]
    immediate_actions: List[str]

class EventData(BaseModel):
    items: List[str]

class CAPAEvent(BaseModel):
    deviation_id: Any
    description: str
    root_cause_category: str
    root_cause_summary: str
    immediate_actions: Optional[str]
    corrective_actions: Optional[str]
    preventive_actions: Optional[str]
    site: str
    model_config = ConfigDict(populate_by_name=True)

class RCSEvent(BaseModel):
    deviation_id: Any
    description: str
    root_cause_category: str
    root_cause_summary: str
    site: str
    model_config = ConfigDict(populate_by_name=True)

class EREvent(BaseModel):
    date_opened: str 
    deviation_id: Any
    description: str
    site: str
    root_cause_summary: str
    age_bucket: str | None = None  # "0_6" or "7_12"



class TimelineEnum(str, Enum):
    zero_to_six_months = "0_to_6_months"
    seven_to_twelve_months = "7_to_12_months"

class ERMonthData(BaseModel):
    title: List[TimelineEnum]
    items: List[str]
    trend: str

class ERSiteData(BaseModel):
    site: str
    total: int = Field(..., description="the total number of deviations having for the particular site")
    categories: List[ERMonthData]

class ERSynth(BaseModel):
    response: List[ERSiteData]