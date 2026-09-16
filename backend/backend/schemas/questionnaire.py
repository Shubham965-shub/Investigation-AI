"""Schemas for interview questionnaire generation (proxies DS POST /interview/questionnaire)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from backend.schemas.common import ArchetypeInfo, EventType, TrackwiseRequest


class QuestionnaireGenerateRequest(TrackwiseRequest):
    pass


class InterviewQuestion(BaseModel):
    description: str
    is_new: bool = False
    is_checked: bool = True


class QuestionnaireGenerateResponse(BaseModel):
    event_type: str
    failure_type: str
    archetype: ArchetypeInfo
    questions: List[InterviewQuestion]
    total_questions_count: int


class QuestionnaireRecord(BaseModel):
    """Investigation record hydrated from the STAR schema; questions is None until generated. Read-only for now."""

    record_id: str
    event_type: EventType
    trackwise_fields: Dict[str, Any]
    questions: Optional[List[InterviewQuestion]] = None
    # See src/schemas/problem_statement.py's stage field for what this means.
    stage: int = 0
