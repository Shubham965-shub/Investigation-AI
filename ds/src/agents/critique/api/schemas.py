from pydantic import BaseModel
from typing import List, Optional

class TaskSchema(BaseModel):
    tick: str                      # task name
    task: str                      # status (Verified / NA / Shall be verified)
    responsible_person: str
    selected: bool = False
    mandatory: bool = False
    mandatory_selected: Optional[bool] = False

class TaskOutSchema(BaseModel):
    tick: str                      # task name
    task: str                      # status (Verified / NA / Shall be verified)
    responsible_person: str
    selected: bool = False
    mandatory: bool = False
    mandatory_selected: Optional[bool] = False
    critique: Optional[str] = ""

class CritiqueInputSchema(BaseModel):
    event_type: str
    problem_statement: List[str]
    tasks: List[TaskSchema]

class CritiqueOutSchema(BaseModel):
    problem_statement: List[str]
    tasks: List[TaskOutSchema]

from typing import List, Optional
from pydantic import BaseModel


# ---------- Event Description ----------

class EventDescriptionData(BaseModel):
    rciNumber: str
    rciOwner: str
    rciInitiatedOn: Optional[str] = None
    parentRecord: Optional[str] = None
    problemStatement: str


class EventDescription(BaseModel):
    section: str
    title: str
    data: EventDescriptionData


# ---------- Prerequisites ----------

class PrerequisiteItem(BaseModel):
    text: str
    response: str
    explanation: str


class Prerequisites(BaseModel):
    section: str
    title: str
    data: List[PrerequisiteItem]


# ---------- Task Assignments ----------

class TaskAssignmentItem(BaseModel):
    tick: str
    task: str
    responsible_person: str
    selected: bool
    critique: Optional[str]
    mandatory: bool


class TaskAssignments(BaseModel):
    section: str
    title: str
    data: List[TaskAssignmentItem]


# ---------- Root Model ----------

class CritiqueRCIRequest(BaseModel):
    eventDescription: EventDescription
    prerequisites: Prerequisites
    taskAssignments: TaskAssignments

class QuestionnaireRequest(BaseModel):
    event_type: str
    problem_statement: str
    preliminary_findings: str

class QuestionnaireResponse(BaseModel):
    question: List[str]


# ---------- RC Conclusion Critique ----------

class RCConclusionCritiqueRequest(BaseModel):
    event_type: str
    problem_statement: str
    investigation_summary: str      # brief summary of what the investigation tasks found
    rc_conclusion_text: str         # section 8 text from the RCI report
    is_repeat_occurrence: Optional[bool] = None


class RCConclusionCritiqueResponse(BaseModel):
    rc_conclusion_text: str
    recommendations: List[str]      # flat list of actionable recommendations, not tagged by rule
    strengths: str                  # 1-2 sentences on what was done well


# ---------- CAPA Critique ----------

class CAPAItemDetail(BaseModel):
    description: str
    responsibility: Optional[str] = None
    due_date: Optional[str] = None


class CAPACritiqueRequest(BaseModel):
    event_type: str
    problem_statement: str
    rc_conclusion_text: str         # section 8 — needed to check CAPA alignment
    investigation_summary: str      # brief summary of gaps found during investigation
    capa_items: List[CAPAItemDetail]
    capa_overall_text: Optional[str] = None   # any free text above the CAPA table


class CAPACritiqueResponse(BaseModel):
    recommendations: List[str]      # flat list of actionable recommendations, not tagged by rule
    strengths: str                  # 1-2 sentences on what was done well


# ---------- Combined RCI Report Critique ----------

class RCIReportCritiqueResponse(BaseModel):
    problem_statement: str
    rc_conclusion: RCConclusionCritiqueResponse
    capa: CAPACritiqueResponse