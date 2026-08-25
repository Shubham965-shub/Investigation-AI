"""Schemas for the RCI Report module (step 7 of 7) — proxies ds's real
POST /rci-report/generate. Field names/types below are copied verbatim from
ds's own schemas (ds/src/agents/rci_report/api/schemas/{define,
measure_analyze,improve_control,common,response}.py, re-read directly
2026-08-21) rather than imported across the service boundary — same
convention rc_capa_critique.py already uses for its own shapes.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from backend.schemas.common import EventType


# ── Shared primitives (ds's common.py) ──────────────────────────────────

class SourcedText(BaseModel):
    """Cross-cutting primitive for fields TrackWise doesn't back for every
    event type. Renders an explicit manual-entry state instead of a
    silently blank string."""
    value: str
    source: Literal["trackwise", "manual_entry_required", "manual_entry_provided", "synthesized"]


class InterimControlItem(BaseModel):
    description: str
    responsibility: str
    due_date: str  # a literal date OR a status word, e.g. "Completed"


class CAPAExtrapolationItem(BaseModel):
    applicable: bool
    justification: str
    scope_description: str
    related_customers: List[str] = Field(default_factory=list)
    related_markets: List[str] = Field(default_factory=list)
    capa_numbers: List[str] = Field(default_factory=list)
    related_change_controls: List[str] = Field(default_factory=list)
    responsibility: str
    due_date: str


class AnnexureItem(BaseModel):
    annexure_no: str
    title: str


class ApprovalRow(BaseModel):
    role: str
    name: Optional[str] = None
    title: Optional[str] = None
    department: Optional[str] = None
    signature_date: Optional[str] = None


class AnnexuresSection(BaseModel):
    """Not LLM-generated — pure pass-through of whatever we send ds."""
    items: List[AnnexureItem] = Field(default_factory=list)


class ApprovalSection(BaseModel):
    """Not LLM-generated — pure pass-through of whatever we send ds."""
    rows: List[ApprovalRow] = Field(default_factory=list)


# ── 1. Executive Summary / Description / Initial Impact (ds's define.py) ─

class ExecutiveSummarySection(BaseModel):
    summary: str
    problem_description: str
    immediate_containment_action: str
    determination_of_root_cause: str
    root_cause_probable_cause_statement: str
    impact_assessment: str
    correction_conclusion_preventive_actions: str
    conclusion_statement: str


class DescriptionOfEventSection(BaseModel):
    what_happened: str
    when_happened: str
    who_identified: str
    where_it_happened: str
    nonconforming_reference: SourcedText
    how_detected: SourcedText


ImpactType = Literal["Direct", "Indirect", "Not applicable"]


class MaterialProductImpactItem(BaseModel):
    material_product_batch: str
    stage: str
    quantity_involved: str
    quantity_on_hold: SourcedText
    type_of_impact: ImpactType


class EquipmentActionChecklist(BaseModel):
    operation_suspended: bool
    on_hold_label_affixed: bool
    other_action_taken: bool
    other_action_specify: str = ""


class EquipmentImpactItem(BaseModel):
    equipment_instrument: SourcedText
    identification_number: SourcedText
    actions_initiated: EquipmentActionChecklist


class InitialImpactAssessmentSection(BaseModel):
    material_product_impacts: List[MaterialProductImpactItem]
    equipment_impacts: List[EquipmentImpactItem]
    immediate_actions: List[str]


# ── 2. History Review / Investigation Task / Root Cause / Impact / Risk
#      (ds's measure_analyze.py) ─────────────────────────────────────────

class HistoryReviewRow(BaseModel):
    event_number: str
    event_title: str
    capa_description: str
    capa_implementation_date: str


class HistoryReviewSection(BaseModel):
    lookback_months: int
    rows: List[HistoryReviewRow]
    no_similar_events_found: bool
    closing_narrative: str
    batches_manufactured_note: Optional[str] = None


RCAMethod = Literal[
    "Why-Why Analysis",
    "Fishbone / Ishikawa",
    "Fault Tree Analysis",
    "Flowchart / Process Mapping",
    "GEMBA Walk",
    "Failure Mode Effective Analysis (FMEA)",
    "Not explicitly stated",
]
SixMFactor = Literal["Man", "Machine", "Material", "Method", "Measurement", "Mother Nature"]


class InvestigationTaskFinding(BaseModel):
    sop_reference: Optional[str] = None
    finding: str


class InvestigationTaskSubsection(BaseModel):
    title: str
    six_m_factors: List[SixMFactor] = Field(default_factory=list)
    findings: List[InvestigationTaskFinding] = Field(default_factory=list)


class InvestigationTaskGroup(BaseModel):
    section_title: str
    subsections: List[InvestigationTaskSubsection] = Field(default_factory=list)


class InvestigationTaskSection(BaseModel):
    rca_method_evidence: str
    rca_methods_used: List[RCAMethod] = Field(default_factory=list)
    groups: List[InvestigationTaskGroup] = Field(default_factory=list)


class RootCauseTaxonomy(BaseModel):
    category: SixMFactor
    sub_category: str


class RootCauseConclusionSection(BaseModel):
    conclusion: str
    taxonomy: RootCauseTaxonomy
    repeat_occurrence_evidence: str
    is_repeat_occurrence: bool


class ImpactSubsection(BaseModel):
    applicable: bool
    narrative: str


class BatchShipperImpact(BaseModel):
    batch_number: str
    number_of_shippers: str
    defects: str


class ImpactOnAffectedBatchSubsection(ImpactSubsection):
    batch_shipper_table: List[BatchShipperImpact] = Field(default_factory=list)


class ImpactAssessmentBatchDispositionSection(BaseModel):
    impact_on_affected_batches: ImpactOnAffectedBatchSubsection
    impact_on_marketed_released_batches: ImpactSubsection
    impact_on_other_product_material_area_process: ImpactSubsection
    impact_on_regulatory_filing: ImpactSubsection
    impact_on_facility_equipment_instrument: ImpactSubsection
    impact_on_manufacturing_process_analytical_method: ImpactSubsection
    business_continuity: ImpactSubsection
    impact_on_data_integrity: ImpactSubsection
    stability_repackaging_requirement: ImpactSubsection
    patient_safety: ImpactSubsection
    others_as_applicable: ImpactSubsection
    conclusion: str
    medical_investigation_summary: Optional[str] = None
    health_hazard_evaluation: Optional[str] = None
    impact_justification: Optional[str] = None


SeverityTier = Literal["Critical", "Medium", "Low"]
RepeatabilityTier = Literal["High", "Medium", "Low"]
DetectabilityTier = Literal["High", "Medium", "Low"]
RiskLevel = Literal["L1", "L2", "L3", "L4", "L5"]


class SeveritySelection(BaseModel):
    grounding_evidence: str
    tier: SeverityTier


class RepeatabilitySelection(BaseModel):
    grounding_evidence: str
    tier: RepeatabilityTier


class DetectabilitySelection(BaseModel):
    grounding_evidence: str
    tier: DetectabilityTier


class RiskFactorScores(BaseModel):
    severity: SeveritySelection
    repeatability: RepeatabilitySelection
    detectability: DetectabilitySelection


class RiskAssessmentCandidate(BaseModel):
    cause_label: str
    factors: RiskFactorScores
    severity_score: int
    repeatability_score: int
    detectability_score: int
    rpn: int
    risk_level: RiskLevel


class RiskAssessmentSection(BaseModel):
    applicability_reason: str
    applicable: Literal["yes", "no — unconfirmed market complaint"]
    candidates: List[RiskAssessmentCandidate] = Field(default_factory=list)


# ── 3. Correction / CAPA / CAPA Effectiveness (ds's improve_control.py) ──

class ObservationStatusItem(BaseModel):
    observation: str
    status: str
    reference_number: Optional[str] = None


class CorrectionRemedialActionSection(BaseModel):
    items: List[ObservationStatusItem] = Field(default_factory=list)
    additional_notes: List[str] = Field(default_factory=list)


class CAPAActionItem(BaseModel):
    description: str
    responsibility: Optional[str] = None
    due_date: str


class CAPASection(BaseModel):
    capa_not_applicable_justification: Optional[str] = None
    capa_actions: List[CAPAActionItem] = Field(default_factory=list)
    interim_controls: List[InterimControlItem] = Field(default_factory=list)
    extrapolation: CAPAExtrapolationItem


DurationTier = Literal["short", "standard", "extended"]
CAPAMechanism = Literal["Procedural / training-based", "Resource / equipment substitution", "Other"]


class CAPAEffectivenessPlanItem(BaseModel):
    grounding_evidence: str
    capa_mechanism: CAPAMechanism
    capa_description: str
    effectiveness_check: List[str] = Field(default_factory=list)
    effectiveness_criteria: List[str] = Field(default_factory=list)
    responsibility: str
    duration_rationale: str
    duration_tier: DurationTier
    monitoring_duration: str


class CAPAEffectivenessCheckPlanSection(BaseModel):
    capa_not_applicable_justification: Optional[str] = None
    generated_plans: List[CAPAEffectivenessPlanItem] = Field(default_factory=list)


# ── Whole report ──────────────────────────────────────────────────────────

class RciReportSections(BaseModel):
    event_type: str
    # Every section is Optional on ds's own RciReportResponse — ds skips a
    # section (leaving it None) rather than failing the whole request when a
    # required TrackWise field is blank, or when a section it depends on was
    # itself skipped (2026-08-24, found live: a Market Complaint missing
    # 'complaint_reported_by'/'impact_details'/'correction_or_remedial_action'
    # nulled out 6 of the 11 sections). Mirrored here the same way, since
    # treating them as required made `RciReportSections(**data)` raise on any
    # real ds response with a skipped section — an unrelated data gap must
    # never break the sections that DID generate.
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
    # Keyed by section field name — ds's explanation for why that section is
    # None (a blank required TrackWise field, or a skipped dependency).
    # Surfaced on the frontend so the investigator knows to go fill the
    # field rather than assuming generation itself is broken.
    errors: Dict[str, str] = Field(default_factory=dict)


class RciReportRecord(BaseModel):
    record_id: str
    event_type: EventType
    trackwise_fields: Dict[str, Any]
    report: Optional[RciReportSections] = None
    generated_at: Optional[datetime.datetime] = None
    # Only relevant for event_type == "Market Complaint" — gates Risk
    # Assessment on ds's side (None -> ds defaults to "applicable").
    mc_confirmed: Optional[bool] = None
    manual_entries: Dict[str, str] = Field(default_factory=dict)
