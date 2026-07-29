from pydantic import BaseModel, Field
from typing import Literal, Union, Annotated, Optional, List

class EvaluateRequest(BaseModel):
    event_type: Literal["Deviation", "OOS", "OOT", "Market Complaint"]
    narrative: str = Field(
        ...,
        description="Free-text description of the event or problem statement"
    )


class ChecklistItem(BaseModel):
    label: str
    present: bool

class CheckList(BaseModel):
    response: List[ChecklistItem]

class ImprovementSuggestion(BaseModel):
    id: int
    title: str
    subtitle: Optional[str] = None
    original: Optional[str] = None
    aiProposed: Optional[str] = None

class ImprovementSuggestionList(BaseModel):
    suggestions: List[ImprovementSuggestion]

class ImmediateActionsResponse(BaseModel):
    event_type: str
    sop_actions: List[str]  # exactly 5 predefined texts
    llm_actions: List[str]  # exactly 5 LLM-generated texts

class LLMActions(BaseModel):
    # exactly 5 strings
    llm_actions: List[str] = Field(min_length=5, max_length=5)


class EvaluateResponse(BaseModel):
    checklist: CheckList = Field(
        description="Evaluation checklist indicating presence/absence of required elements"
    )

    suggestions: ImprovementSuggestionList = Field(
        description="AI-generated improvement suggestions"
    )


class ProblemStatementResponse(BaseModel):
    problem_statements: List[str] = Field(
        description="List of individual problem statement items extracted from the document"
    )


