from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field
from datetime import date


# -------------------------
# Section 1.1 – Event Description
# -------------------------

from datetime import date
from pydantic import BaseModel, Field
from typing import Optional


class RCIHeader(BaseModel):
    rci_number: Optional[str] = None
    rci_owner: Optional[str] = None

    initiated_on_raw: Optional[str] = Field(
        None,
        description="Date exactly as written in the document (e.g. 17/12/2024)"
    )
    initiated_on: Optional[date] = Field(
        None,
        description="Normalized ISO date (YYYY-MM-DD). Null if ambiguous."
    )

    parent_record: Optional[str] = None

    parent_record_date_raw: Optional[str] = Field(
        None,
        description="Date exactly as written in the document"
    )
    parent_record_date: Optional[date] = Field(
        None,
        description="Normalized ISO date (YYYY-MM-DD). Null if ambiguous."
    )


class ProblemStatement(BaseModel):
    label: str = Field(
        "Problem statement",
        description="Label used in the document"
    )
    items: List[str] = Field(
        default_factory=list,
        description="Narrative problem statement items"
    )


class ObservationDetail(BaseModel):
    test_name: str
    hts_frequency: Optional[str] = None
    oot_criteria: Optional[str] = None
    specification_limit: Optional[str] = None
    reported_result: Optional[str] = None


class OtherDetails(BaseModel):
    product_name: Optional[str] = None
    batch_type: Optional[str] = None
    market: Optional[str] = None
    mfg_date: Optional[str] = None
    exp_date: Optional[str] = None
    specification_number: Optional[str] = None
    stp_number: Optional[str] = None
    analyst_name: Optional[str] = None


class QANotification(BaseModel):
    message: Optional[str] = None




class SectionField(BaseModel):
    key: str = Field(..., description="Field name as it appears logically")
    value: Union[str, List[str]] = Field(
        ...,
        description="Exact extracted value; text or list of text blocks"
    )

class DynamicSection(BaseModel):
    section_type: str = Field(
        ...,
        description="Logical identifier like problem_statement, observation_details"
    )
    title: Optional[str] = None

    fields: List[SectionField] = Field(
        default_factory=list,
        description="Extracted fields belonging to this section"
    )

class EventDescriptionSection(BaseModel):
    section_number: str = Field("1.1")
    title: str = Field("Event Description")

    rci_header: Optional[RCIHeader] = None
    
    sections: List[DynamicSection] = Field(
        default_factory=list,
        description="Variable subsections identified by the LLM"
    )

# -------------------------
# Section 1.2 – Prerequisites
# -------------------------

class PrerequisiteChoice(BaseModel):
    label: Literal["Yes", "No", "N/A"]
    selected: bool


class PrerequisiteItem(BaseModel):
    sr: Optional[str] = None
    prerequisite: str
    choices: List[PrerequisiteChoice] = Field(
        ...,
        description="Only ONE true value permitted"
    )

    explanation: Optional[str] = None


class PrerequisitesSection(BaseModel):
    section_number: str = Field("1.2")
    title: str = Field("Pre-requisite of Investigation Plan")
    items: List[PrerequisiteItem] = Field(default_factory=list)


# -------------------------
# Section 2.2 – Sign-off
# -------------------------

class Signatory(BaseModel):
    role: str
    name: Optional[str] = None


class SignOffSection(BaseModel):
    section_number: str = Field("2.2")
    title: str = Field("RCI Plan Sign-off")
    signatories: List[Signatory] = Field(default_factory=list)


# -------------------------
# ✅ Overall Return Schema
# -------------------------

class TaskAssignmentItem(BaseModel):
    """
    Represents one row in Section 2.1 – Identification of Investigation Team
    members & Task Assignment.
    """

    selected: Optional[bool] = Field(
        default=None,
        description="Whether the task is selected (checked / ticked) in the document"
    )

    task: Optional[str] = Field(
        default=None,
        description="Exact task name as written in the document"
    )

    status: Optional[str] = Field(
        default=None,
        description="Remarks / status / description provided for the task"
    )

    responsible_person: Optional[str] = Field(
        default=None,
        description="Name of responsible person exactly as written"
    )

    mandatory: Optional[bool] = Field(
        default=None,
        description="True if the task is marked mandatory (prefixed with *)"
    )


class TaskAssignmentsSection(BaseModel):
    """
    Section 2.1 – Identification of Investigation Team members & Task Assignment
    """

    section_number: str = Field(default="2.1")

    title: Optional[str] = Field(
        default="Identification of Investigation Team members & Task Assignment"
    )

    items: List[TaskAssignmentItem] = Field(default_factory=list)

class RCIPlanExtract(BaseModel):
    """
    Combined structured extraction result for the RCI Plan
    """

    event_description: Optional[EventDescriptionSection] = None
    prerequisites: Optional[PrerequisitesSection] = None
    task_assignments: Optional[TaskAssignmentsSection] = None
    signoff: Optional[SignOffSection] = None


