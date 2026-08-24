"""Schemas for RCI plan generation (proxies DS POST /rci/plan and /rci/upload)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from backend.schemas.common import ArchetypeInfo, EventType, TrackwiseRequest


class RciPlanGenerateRequest(TrackwiseRequest):
    pass


class RciTaskItem(BaseModel):
    description: str
    is_checked: bool = True


class RciSectionItem(BaseModel):
    title: str
    correlation: Optional[str] = None
    six_m_bucket: Optional[str] = None
    tasks: List[RciTaskItem]
    # Populated only when read back from investigation_rci_sections
    # (generated_content.sql) — DS's generate response doesn't return these
    # yet (see project memory: rci-plan-schema-gap).
    due_date: Optional[str] = None
    assignee: Optional[str] = None
    # investigation_rci_sections.id — only populated on read-back (never on a
    # freshly-generated, not-yet-persisted DS response). Consumed by Task
    # Critique to attach report/recommendation history to a specific section.
    id: Optional[int] = None


class RciPlanGenerateResponse(BaseModel):
    event_type: str
    failure_type: str
    archetype: ArchetypeInfo
    sections: List[RciSectionItem]
    total_sections_count: int
    total_tasks_count: int


class RciPlanRecord(BaseModel):
    """A real investigation record's Trackwise fields, hydrated from the STAR
    schema. sections is None until a plan has been generated and persisted to
    investigation_rci_sections/investigation_rci_tasks (generated_content.sql);
    read-only for now."""

    record_id: str
    event_type: EventType
    trackwise_fields: Dict[str, Any]
    sections: Optional[List[RciSectionItem]] = None
    # See src/schemas/problem_statement.py's stage field for what this means.
    stage: int = 0
    # True once any section has Task Critique history (a report uploaded) —
    # RCI Plan becomes read-only at that point, since further edits here
    # would delete-then-recreate investigation_rci_sections rows (fresh IDs),
    # cascading away that Task Critique history (2026-08-05, per the user).
    locked_for_editing: bool = False


class RciTemplateUploadResponse(BaseModel):
    status: str
    message: str
    archetypes_processed: List[str]
    plans_created: int
    sections_created: int
    tasks_created: int
