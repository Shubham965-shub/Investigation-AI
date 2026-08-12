from typing import List

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
    executive_summary: ExecutiveSummarySection
    description_of_event: DescriptionOfEventSection
    initial_impact_assessment: InitialImpactAssessmentSection
    history_review: HistoryReviewSection
    investigation_task: InvestigationTaskSection
    root_cause_conclusion: RootCauseConclusionSection
    impact_assessment_batch_disposition: ImpactAssessmentBatchDispositionSection
    risk_assessment: RiskAssessmentSection
    correction_remedial_action: CorrectionRemedialActionSection
    capa: CAPASection
    capa_effectiveness_check_plan: CAPAEffectivenessCheckPlanSection
    annexures: AnnexuresSection = Field(default_factory=AnnexuresSection)
    approval: ApprovalSection = Field(default_factory=ApprovalSection)
