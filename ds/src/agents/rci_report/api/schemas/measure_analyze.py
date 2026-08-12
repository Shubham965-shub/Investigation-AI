import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

# CJK, Hiragana/Katakana, Hangul, Cyrillic, Arabic, Devanagari, Thai — none of these
# scripts are ever legitimate in an English-language pharma QA report; a match means
# a garbled/mixed-language generation artifact, not a real word.
_NON_LATIN_SCRIPT_RE = re.compile(
    r"[一-鿿぀-ヿ가-힣Ѐ-ӿ؀-ۿऀ-ॿ฀-๿]"
)


class HistoryReviewRow(BaseModel):
    event_number: str
    event_title: str
    capa_description: str
    capa_implementation_date: str  # sourced from a QA e-signature closure date, not a planned date — see GAPS.md


class HistoryReviewSection(BaseModel):
    lookback_months: int
    rows: List[HistoryReviewRow]
    no_similar_events_found: bool
    closing_narrative: str  # e.g. "Global CAPA was verified and found no action for similar failure."
    # Added 2026-08-09: all three Word templates require this ("...brief of several
    # batches manufactured... in the review period"), and both real reports checked
    # render it. No confirmed structured data source exists yet for a genuine
    # batches-manufactured count (this is NOT the same table/query as the similar-
    # events search above) — sourced from manual_entries only until one is found; see
    # GAPS.md. Optional/None rather than a SourcedText, since "not yet sourceable" is
    # a data-pipeline gap, not a per-record manual-entry state to render to a user.
    batches_manufactured_note: Optional[str] = None

    @model_validator(mode="after")
    def _flag_matches_rows(self):
        if self.no_similar_events_found and self.rows:
            raise ValueError("no_similar_events_found is True but rows is non-empty")
        return self


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
    sop_reference: Optional[str] = None  # e.g. "GMS/001" — cite when grounded in a specific SOP
    finding: str


class InvestigationTaskSubsection(BaseModel):
    title: str  # e.g. "RECEIPT OF DAMAGED CONTAINERS"
    # Was a single SixMFactor -- changed 2026-08-09 to a non-empty list, since a
    # cross-cutting synthesis subsection (e.g. a real Market Complaint report's
    # "Brainstorming" round-up, which evaluates causes spanning Method/Machine/
    # Measurement together) can't be forced into one bucket. min_length=1 enforces
    # this deterministically, not just via the prompt's own instruction. See GAPS.md.
    six_m_factors: List[SixMFactor] = Field(..., min_length=1)
    findings: List[InvestigationTaskFinding]


class InvestigationTaskGroup(BaseModel):
    """Added 2026-08-09: real reports render a two-level hierarchy this section
    used to flatten away. Two confirmed real shapes this must cover: (1) a
    Deviation-style umbrella heading per RCI-Plan section ("Raw Material Receipt
    and Storage") containing several granular task subsections; (2) a Market
    Complaint/Fishbone-style report organized around 6M-factor headings ("Man",
    "Material"...) as the group itself, each with one or more subsections. See
    GAPS.md.
    """
    section_title: str  # RCI Plan section title, OR a 6M-factor/theme name for Fishbone-style reports
    subsections: List[InvestigationTaskSubsection]


class InvestigationTaskSection(BaseModel):
    rca_method_evidence: str  # reasoning first
    # A real investigation commonly names several methods used together (e.g. Process
    # Mapping + GEMBA Walk + FMEA) -- a single value would force dropping the others.
    rca_methods_used: List[RCAMethod]
    groups: List[InvestigationTaskGroup]  # was a flat `subsections` list -- see InvestigationTaskGroup

    @model_validator(mode="after")
    def _no_stray_non_latin_characters(self):
        # Found live (2026-08-06): rca_method_evidence came back with a garbled CJK
        # character mixed into otherwise-English prose ("a现场/GEMBA-style shop-floor
        # walk"). This is a pharma QA report written in English -- non-Latin script
        # is never legitimate here; catch it deterministically and retry rather than
        # rely on prompt wording alone.
        if _NON_LATIN_SCRIPT_RE.search(self.rca_method_evidence):
            raise ValueError(f"rca_method_evidence contains stray non-Latin characters: {self.rca_method_evidence!r}")
        for group in self.groups:
            if _NON_LATIN_SCRIPT_RE.search(group.section_title):
                raise ValueError(f"group section_title contains stray non-Latin characters: {group.section_title!r}")
            for sub in group.subsections:
                if _NON_LATIN_SCRIPT_RE.search(sub.title):
                    raise ValueError(f"subsection title contains stray non-Latin characters: {sub.title!r}")
                for f in sub.findings:
                    if _NON_LATIN_SCRIPT_RE.search(f.finding):
                        raise ValueError(f"finding contains stray non-Latin characters: {f.finding!r}")
        return self


class RootCauseTaxonomy(BaseModel):
    """2-tier taxonomy — corrected 2026-08-09. The previous 3-tier model
    (broad_category/category/sub_category, mirroring the DB columns
    broad_category/category/root_cause_sub_category) was checked against the
    ACTUAL RENDERED real reports for the very same records those DB values came
    from, across all 4 event types (Deviation, MC, OOS, OOT) — none of them render
    that 3-tier scheme. All four instead show a 2-tier shape: a 6M-factor category
    (e.g. "Root cause-category: Method") plus a free-text sub-category (e.g.
    "Subcategory: Deficient instruction"). See GAPS.md.
    """
    category: SixMFactor  # e.g. "Method" — normalize close variants (e.g. real OOS report's "Procedural") into the 6M vocabulary
    sub_category: str  # e.g. "Deficient instruction", "Inadequate checkpoints in the procedure"


class RootCauseConclusionSection(BaseModel):
    conclusion: str  # cause + brief mechanism ONLY — no derivation detail (prompt-enforced, not schema-validated)
    taxonomy: RootCauseTaxonomy
    repeat_occurrence_evidence: str  # reasoning first — cites OOS Repeat occurrence field or narrative signal
    is_repeat_occurrence: bool


class ImpactSubsection(BaseModel):
    applicable: bool
    narrative: str  # "NA - no impact" when not applicable


class BatchShipperImpact(BaseModel):
    batch_number: str
    number_of_shippers: str
    defects: str  # "None" if no defects


class ImpactOnAffectedBatchSubsection(ImpactSubsection):
    batch_shipper_table: List[BatchShipperImpact] = Field(default_factory=list)


class ImpactAssessmentBatchDispositionSection(BaseModel):
    """12 discrete subsections, confirmed from the real UI screenshot — NOT the
    Word template's single "Conclusion Statement" blob.
    """
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
    conclusion: str  # synthesizes the 11 subsections above into the final disposition
    medical_investigation_summary: Optional[str] = None  # MC only
    health_hazard_evaluation: Optional[str] = None  # MC only
    impact_justification: Optional[str] = None  # OOS/OOT only

    @model_validator(mode="after")
    def _others_not_verbatim_duplicate_of_patient_safety(self):
        # Directly encodes the exact bug found in rci_report_section_inputs.md §7:
        # "Others as applicable" repeated the exact same two bullets as "Patient
        # Safety" verbatim in the one real example record.
        if (
            self.others_as_applicable.applicable
            and self.others_as_applicable.narrative.strip()
            and self.others_as_applicable.narrative.strip() == self.patient_safety.narrative.strip()
        ):
            raise ValueError(
                "others_as_applicable duplicates patient_safety verbatim — identify "
                "genuinely distinct content or set others_as_applicable.applicable=False"
            )
        return self

    @model_validator(mode="after")
    def _applicable_true_never_paired_with_na_narrative(self):
        # Found live (2026-08-06): impact_on_other_product_material_area_process came
        # back applicable=True with narrative "NA — the event was limited to...", a
        # self-contradictory pairing. "NA" narrative content always means
        # applicable=False, across all 11 subsections — not just the
        # others_as_applicable/patient_safety pair guarded above.
        for field_name in (
            "impact_on_affected_batches",
            "impact_on_marketed_released_batches",
            "impact_on_other_product_material_area_process",
            "impact_on_regulatory_filing",
            "impact_on_facility_equipment_instrument",
            "impact_on_manufacturing_process_analytical_method",
            "business_continuity",
            "impact_on_data_integrity",
            "stability_repackaging_requirement",
            "patient_safety",
            "others_as_applicable",
        ):
            sub = getattr(self, field_name)
            if sub.applicable and sub.narrative.strip().upper().startswith("NA"):
                raise ValueError(
                    f"{field_name}.applicable is True but narrative starts with 'NA' "
                    f"({sub.narrative.strip()!r}) — 'NA' content always means applicable=False"
                )
        return self


SeverityTier = Literal["Critical", "Medium", "Low"]
# Canonical name is "Repeatability" (matches the Word template + the UI's own row
# label). The UI's formula callout says "Recurrence" instead, and its result column
# literally renders "RNP" — both are treated as UI typos, never propagated into a
# field name. See GAPS.md.
RepeatabilityTier = Literal["High", "Medium", "Low"]
DetectabilityTier = Literal["High", "Medium", "Low"]
RiskLevel = Literal["L1", "L2", "L3", "L4", "L5"]
# Score lookup tables and the RPN/band computation itself live in
# api/services/risk_scoring.py, not here — this module only defines data shapes.


class SeveritySelection(BaseModel):
    grounding_evidence: str  # reasoning first; the score itself comes from a lookup table, never the LLM
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


class GeneratedRiskFactors(BaseModel):
    """The actual `structure=` passed to get_structured_response for Section 8.
    Tiers + grounding + applicability only — score/RPN/band are never
    LLM-authored, see risk_scoring.py for the deterministic computation.
    """
    applicability_reason: str
    applicable: Literal["yes", "no — unconfirmed market complaint"]
    candidate_labels: List[str] = Field(default_factory=list)  # e.g. "Root cause", "Probable cause 1"
    candidates: List[RiskFactorScores] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistency(self):
        if self.applicable.startswith("no") and (self.candidates or self.candidate_labels):
            raise ValueError("applicable is 'no' but candidates/candidate_labels is non-empty")
        if self.applicable == "yes":
            if not self.candidates:
                raise ValueError("applicable is 'yes' but no candidates were scored")
            if len(self.candidates) != len(self.candidate_labels):
                raise ValueError("candidates and candidate_labels must be the same length")
        return self


class RiskAssessmentCandidate(BaseModel):
    cause_label: str
    factors: RiskFactorScores
    severity_score: int  # computed in risk_scoring.py, never LLM output
    repeatability_score: int
    detectability_score: int
    rpn: int  # = product of the three scores above, computed
    risk_level: RiskLevel  # banded from rpn per the template's L1-L5 thresholds, computed


class RiskAssessmentSection(BaseModel):
    applicability_reason: str
    applicable: Literal["yes", "no — unconfirmed market complaint"]
    candidates: List[RiskAssessmentCandidate] = Field(default_factory=list)
