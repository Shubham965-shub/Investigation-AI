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
    # Deterministic disclosure of the search itself (query seed, fields, scope) — the
    # template explicitly asks for this ("Keywords used for running the query, the
    # date range, the scope used, etc.") but only the date range (lookback_months)
    # used to be surfaced; this fills the rest. Built in history_review_service.py
    # from the actual search call's own parameters, not LLM-authored.
    search_scope_note: str
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


SixMFactor = Literal["Man", "Machine", "Material", "Method", "Measurement", "Mother Nature"]


class TaskSummaryItem(BaseModel):
    tick: str  # matches TaskAssignmentItem.tick, e.g. "1.2"
    title: str  # short synthesized title/objective for this task, e.g. "VERIFICATION OF DISPENSING AREA SOP"
    six_m_factor: SixMFactor  # primary 6M factor this task's objective addresses
    outcome: str  # 1-2 sentence synthesized outcome/finding from this task's critique/report content


class InvestigationTaskSummarySection(BaseModel):
    """Part 1: brief overall narrative + one row per task actually carried out,
    synthesized from the RCI Plan's own task list and the Task Critique step's
    per-task critique text (which already carries the uploaded task report's
    stored summary — see investigation_task_critique_reports.summary)."""
    overview: str  # 2-4 sentences summarizing overall investigation activity across all tasks
    tasks: List[TaskSummaryItem] = Field(..., min_length=1)


class RootCauseTaskLink(BaseModel):
    tick: str
    title: str
    six_m_factor: SixMFactor
    explanation: str  # why this specific task's evidence supports the accepted root/probable cause


class RootCauseIdentificationSection(BaseModel):
    """Part 2: explanation limited to ONLY the task(s) whose findings actually
    identified the root/probable cause -- not every task carried out."""
    grounding_evidence: str  # reasoning first, tying the accepted RC conclusion to specific task(s) below
    applicable_tasks: List[RootCauseTaskLink] = Field(..., min_length=1)


class WhyWhyStep(BaseModel):
    question: str
    answer: str


class WhyWhyAnalysisSection(BaseModel):
    """Part 2: the Why-Why chain tracing the accepted root cause -- the only
    RCA demonstration this report ever renders (2026-09-01, per the user;
    Fishbone/Ishikawa, Fault Tree, and Flowchart/Process Mapping dropped
    entirely, along with the "pick whichever method fits" logic they used
    to require)."""
    six_m_factor: SixMFactor  # the single dominant 6M factor this chain traces
    method_rationale: str  # reasoning first: why the evidence supports this chain
    why_why_chain: List[WhyWhyStep] = Field(..., min_length=1)


class InvestigationTaskSection(BaseModel):
    task_summary: InvestigationTaskSummarySection
    why_why_analysis: WhyWhyAnalysisSection
    root_cause_identification: RootCauseIdentificationSection

    @model_validator(mode="after")
    def _no_stray_non_latin_characters(self):
        # This is a pharma QA report written in English -- non-Latin script is
        # never legitimate here; catch it deterministically and retry rather
        # than rely on prompt wording alone (see the pre-2026-08-25 shape of
        # this validator in GAPS.md for the original live-found bug).
        texts = [self.task_summary.overview, self.root_cause_identification.grounding_evidence]
        for t in self.task_summary.tasks:
            texts += [t.title, t.outcome]
        for link in self.root_cause_identification.applicable_tasks:
            texts += [link.title, link.explanation]
        texts.append(self.why_why_analysis.method_rationale)
        texts += [s.question for s in self.why_why_analysis.why_why_chain] + [
            s.answer for s in self.why_why_analysis.why_why_chain
        ]
        for text in texts:
            if _NON_LATIN_SCRIPT_RE.search(text):
                raise ValueError(f"contains stray non-Latin characters: {text!r}")
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
    # Never LLM-drafted (2026-09-01, per the user) -- the route always overrides this
    # with either the uploaded document's own verbatim conclusion or an explicit "not
    # stated" note; the LLM is instructed to always return "" here (see
    # impact_batch_disposition_system.txt item 12).
    conclusion: str
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
