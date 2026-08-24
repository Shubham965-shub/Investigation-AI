from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from src.agents.rci_report.api.schemas.common import AnnexureItem, ApprovalRow
from src.agents.rci_report.api.schemas.define import (
    DescriptionOfEventSection,
    ExecutiveSummarySection,
    InitialImpactAssessmentSection,
)
from src.agents.rci_report.api.schemas.improve_control import (
    CAPAEffectivenessCheckPlanSection,
    CAPASection,
    CorrectionRemedialActionSection,
)
from src.agents.rci_report.api.schemas.measure_analyze import (
    HistoryReviewSection,
    ImpactAssessmentBatchDispositionSection,
    InvestigationTaskSection,
    RiskAssessmentSection,
    RootCauseConclusionSection,
)


class AnnexuresSection(BaseModel):
    """Not LLM-generated — ds has no source for the evidence/attachment manifest.
    Pure pass-through of whatever the backend supplies in the request.
    """
    items: List[AnnexureItem] = Field(default_factory=list)


class ApprovalSection(BaseModel):
    """Not LLM-generated — ds has no source for workflow/role config.
    Pure pass-through of whatever the backend supplies in the request.
    """
    rows: List[ApprovalRow] = Field(default_factory=list)


class RciReportResponse(BaseModel):
    event_type: str
    executive_summary: Optional[ExecutiveSummarySection] = None
    description_of_event: Optional[DescriptionOfEventSection] = None
    initial_impact_assessment: Optional[InitialImpactAssessmentSection] = None
    history_review: Optional[HistoryReviewSection] = None
    investigation_task: Optional[InvestigationTaskSection] = None
    root_cause_conclusion: Optional[RootCauseConclusionSection] = None
    impact_assessment_batch_disposition: Optional[ImpactAssessmentBatchDispositionSection] = None
    risk_assessment: Optional[RiskAssessmentSection] = None
    correction_remedial_action: Optional[CorrectionRemedialActionSection] = None
    capa: Optional[CAPASection] = None
    capa_effectiveness_check_plan: Optional[CAPAEffectivenessCheckPlanSection] = None
    annexures: AnnexuresSection = Field(default_factory=AnnexuresSection)
    approval: ApprovalSection = Field(default_factory=ApprovalSection)
    # Keyed by section field name above (e.g. "root_cause_conclusion"). A section
    # missing here and null in its field failed to generate for an unexpected
    # reason; a section missing here but present failed because a Wave-1
    # dependency it needs also failed — see the skip messages in that case.
    errors: Dict[str, str] = Field(default_factory=dict)
