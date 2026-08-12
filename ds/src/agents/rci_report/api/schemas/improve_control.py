from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from src.agents.rci_report.api.schemas.common import CAPAExtrapolationItem, InterimControlItem


class ObservationStatusItem(BaseModel):
    observation: str
    # Corrected 2026-08-09: real reports render the reference number EMBEDDED
    # verbatim in this one field (e.g. "SAP notification#10243982 initiated for the
    # replacement") — status is no longer stripped of it. reference_number below is
    # an ADDITIVE structured pull-out for consumers that want it separately, not an
    # extraction that empties it out of status. See GAPS.md.
    status: str  # e.g. "Replaced with new cable.", "SAP notification#10243982 initiated for the replacement."
    reference_number: Optional[str] = None  # SAP / change-control / destruction-note reference, when one exists — duplicated from status, not extracted out of it


class CorrectionRemedialActionSection(BaseModel):
    """UI-confirmed shape — abandons the Word template's Correction-vs-Remedial
    narrative split entirely. Real reports pair each observation with a status
    and optional reference number instead.
    """
    items: List[ObservationStatusItem]
    additional_notes: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _not_fully_blank(self):
        # Added 2026-08-09: a real event always has SOME correction/remedial content
        # (that's what closes the investigation) — unlike CAPA/Risk Assessment, this
        # section has no "not applicable" escape valve, so an entirely empty result
        # is never legitimate. See GAPS.md.
        if not self.items and not self.additional_notes:
            raise ValueError("items and additional_notes are both empty — every event has some correction/remedial content")
        return self


class CAPAActionItem(BaseModel):
    description: str  # description + reference folded together, per confirmed UI ("CAPA DESCRIPTION/PR NUMBER")
    # Made Optional 2026-08-09: was required, but upstream CAPAItemDetail.responsibility
    # is itself Optional, and the real Market Complaint report's CAPA table (unlike the
    # Deviation report's) has NO Responsibility column at all — forcing this field
    # required made the model fabricate a plausible value for MC rows where none
    # exists. See GAPS.md.
    responsibility: Optional[str] = None
    due_date: str  # literal date OR a status string ("Completed", "As per change control due date")


class CAPASection(BaseModel):
    capa_not_applicable_justification: Optional[str] = None
    capa_actions: List[CAPAActionItem] = Field(default_factory=list)
    interim_controls: List[InterimControlItem] = Field(default_factory=list)
    extrapolation: CAPAExtrapolationItem

    @model_validator(mode="after")
    def _not_applicable_consistency(self):
        if self.capa_not_applicable_justification and self.capa_actions:
            raise ValueError("capa_not_applicable_justification is set but capa_actions is non-empty")
        # Added 2026-08-09: the original validator only guarded the simultaneous
        # case — a silently blank CAPA section (neither justification nor actions)
        # passed untouched. See GAPS.md.
        if not self.capa_not_applicable_justification and not self.capa_actions:
            raise ValueError("capa_not_applicable_justification is not set and capa_actions is empty — one of the two must hold")
        return self


DurationTier = Literal["short", "standard", "extended"]
CAPAMechanism = Literal["Procedural / training-based", "Resource / equipment substitution", "Other"]


class CAPAEffectivenessPlanItem(BaseModel):
    """One row of Section 11 — one per accepted CAPA action (confirmed against
    the real production UI, 2026-08-06: 2 CAPA actions, 2 rows).

    Deliberately NOT a reuse of capa_depth_effectiveness's GeneratedEffectivenessPlan
    (2026-08-06 correction, see GAPS.md): that type was designed for retroactively
    analysing an ALREADY-COMPLETED report document (it reads the real report's own
    text, redacted of section 12, to infer what the plan should say) — a
    fundamentally different task from rci_report's, which drafts Section 11 before
    any such document exists at all. There is no "actual report" for this module to
    read, ever; forking rather than reusing avoids silently assuming one.
    """
    # Reasoning FIRST: the CAPA action's mechanism, its link to the root cause, and
    # any named individual found in the input (see grounding fields below) — before
    # committing to the fields that follow.
    grounding_evidence: str
    capa_mechanism: CAPAMechanism  # drives what kind of check/criteria makes sense below
    capa_description: str  # restated from the one accepted CAPA action this row covers
    # Changed to List[str] 2026-08-09 (was str) — real reports render both fields as
    # multi-bullet checklists (e.g. "Verify training completion...", "Observe 5-line
    # clearance activities.", "Monitor line clearance records for 30 batches..."),
    # not one merged sentence. This was flagged as an open question when Section 11
    # was first forked (2026-08-06) and never revisited — see GAPS.md.
    effectiveness_check: List[str]  # one bullet per distinct monitoring/verification activity — tailored to capa_mechanism:
    # a Procedural/training-based fix needs training-completion + direct-observation checks;
    # a Resource/equipment-substitution fix needs procurement/rollout verification instead.
    effectiveness_criteria: List[str]  # one bullet per distinct pass/fail criterion, matching capa_mechanism the same way
    responsibility: str  # prefer a named individual from context; "QA" only as a last resort
    duration_rationale: str
    duration_tier: DurationTier
    monitoring_duration: str  # "<N> batches or <M> days, whichever is earlier"


class CAPAEffectivenessCheckPlanSection(BaseModel):
    capa_not_applicable_justification: Optional[str] = None
    generated_plans: List[CAPAEffectivenessPlanItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _not_applicable_consistency(self):
        if self.capa_not_applicable_justification and self.generated_plans:
            raise ValueError("capa_not_applicable_justification is set but generated_plans is non-empty")
        # Added 2026-08-09: same gap as CAPASection — a silently blank result
        # (neither justification nor plans) previously passed untouched.
        if not self.capa_not_applicable_justification and not self.generated_plans:
            raise ValueError("capa_not_applicable_justification is not set and generated_plans is empty — one of the two must hold")
        return self
