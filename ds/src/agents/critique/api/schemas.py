from pydantic import BaseModel
from typing import List, Literal, Optional

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


# ---------- Previously accepted recommendation carry-forward ----------

class PreviousRecommendationCheck(BaseModel):
    """Forces an explicit, evidence-grounded verdict per previously accepted recommendation
    before the model writes the final `recommendations` list (2026-08-14, per the user —
    a bundled single-pass judgment on 'is this specific prior concern resolved?' proved
    imprecise in live testing; requiring a cited quote per item, generated before
    `recommendations` in field order, is the cheap first fix to try before reaching for a
    stronger model or a separate per-item verification call)."""
    recommendation: str              # the previous recommendation being checked, verbatim
    resolved: bool                   # true only if the CURRENT document genuinely resolves it
    evidence: str                    # quote/reference to the specific current-document text the verdict rests on


# ---------- RC Conclusion Critique ----------

class RCConclusionCritiqueRequest(BaseModel):
    event_type: str
    problem_statement: str
    investigation_summary: str      # brief summary of what the investigation tasks found
    rc_conclusion_text: str         # section 8 text from the RCI report
    is_repeat_occurrence: Optional[bool] = None


class RCConclusionCritiqueResponse(BaseModel):
    # Overwritten by critique_route.py after the critique LLM call returns — sourced from the
    # report's own verbatim Section 7/8 text (extract_rci_report_sections, no LLM; not the
    # model's echo), then condensed to 3-4 plain-language sentences by a separate LLM pass
    # (condense_summary.txt) that's forbidden from adding any fact not already in that text.
    rc_conclusion_text: str
    # Declared before `recommendations` so structured-output generation reasons through each
    # previously accepted item, with cited evidence, before writing the final list.
    previous_recommendation_checks: List[PreviousRecommendationCheck] = []
    recommendations: List[str]      # flat list of actionable recommendations, not tagged by rule


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
    # "missing": no CAPA section in the document at all (a document defect — the upload should be
    # rejected and the investigator asked to reupload with CAPA included, see critique_route.py).
    # "not_required": the report itself states/justifies that no CAPA is needed for this event.
    # "evaluated": a real CAPA section was critiqued normally (recommendations below apply).
    capa_status: Literal["missing", "not_required", "evaluated"] = "evaluated"
    previous_recommendation_checks: List[PreviousRecommendationCheck] = []
    recommendations: List[str]      # flat list of actionable recommendations, not tagged by rule
    # Set by critique_route.py after the critique LLM call returns — sourced from the CAPA
    # section text extracted from the report itself (extract_rci_report_sections, no LLM),
    # then condensed to 3-4 plain-language sentences (see rc_conclusion_text above for the
    # same pattern).
    capa_text: str = ""