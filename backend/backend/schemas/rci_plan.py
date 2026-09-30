"""Schemas for RCI plan generation (proxies DS POST /rci/plan and /rci/upload)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.schemas.common import ArchetypeInfo, EventType, TrackwiseRequest


class RciPlanGenerateRequest(TrackwiseRequest):
    pass


class RciTaskItem(BaseModel):
    description: str
    is_checked: bool = True


class RciSectionItem(BaseModel):
    title: str
    correlation: Optional[str] = None
    tasks: List[RciTaskItem]
    # Whole-section include/exclude from the final plan.
    is_checked: bool = True
    # Only populated on read-back — DS's generate response doesn't return these.
    due_date: Optional[str] = None
    assignee: Optional[str] = None
    # investigation_rci_sections.id, read-back only. Consumed by Task Critique to attach history to a specific section.
    id: Optional[int] = None


class RciPrerequisiteChecklist(BaseModel):
    """"1.5 Pre-requisite of Investigation Plan" — a human-filled compliance checklist, same
    nature as a section's manual due_date/assignee; never LLM-generated."""

    bench_top_verification_done: bool = False
    preliminary_checklist_done: bool = False
    personnel_interview_done: bool = False
    photographic_evidence_collected: bool = False


class RciPlanGenerateResponse(BaseModel):
    event_type: str
    failure_type: str
    archetype: ArchetypeInfo
    sections: List[RciSectionItem]
    total_sections_count: int
    total_tasks_count: int


class RciPlanRecord(BaseModel):
    """Investigation record hydrated from the STAR schema; sections is None until a plan has been generated. Read-only for now."""

    record_id: str
    event_type: EventType
    trackwise_fields: Dict[str, Any]
    sections: Optional[List[RciSectionItem]] = None
    stage: int = 0
    # True once any section has Task Critique history — further edits would delete/recreate section rows and lose that history.
    locked_for_editing: bool = False
    prerequisite_checklist: RciPrerequisiteChecklist = Field(default_factory=RciPrerequisiteChecklist)


class RciTemplateUploadResponse(BaseModel):
    status: str
    message: str
    archetypes_processed: List[str]
    plans_created: int
    sections_created: int
    tasks_created: int
