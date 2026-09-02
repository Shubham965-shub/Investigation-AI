from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional

from src.agents.critique.api.schemas import CAPAItemDetail, TaskAssignmentItem
from src.agents.rci_plan.schemas import RciSectionItem
from src.agents.rci_report.api.schemas.request import (
    AcceptedCAPAProposal,
    AcceptedRCConclusion,
    RciReportGenerationRequest,
)
from src.agents.shared.schemas import missing_required_trackwise_fields, required_trackwise_fields


@dataclass(frozen=True)
class RciReportContext:
    """Built once per request, read (never written) by up to 9 concurrent
    Wave-1 tasks. Frozen so "no shared mutable state" is a compile-time
    guarantee (FrozenInstanceError), not just a convention — the direct fix
    for the one real correctness risk of concurrent section generation.
    """
    event_type: str
    deviation_id: Optional[str]
    trackwise_fields: Dict[str, Any]  # snake_case keys (by_alias=False), matches live DB column names
    # Attribute names (from missing_required_trackwise_fields) of TW fields the
    # request-level validator would previously have hard-rejected the whole
    # request for — now surfaced so the route can skip only the section(s)
    # that actually need them (see _SECTION_REQUIRED_TW_FIELDS).
    missing_required_tw_fields: FrozenSet[str]
    # Total required-field universe (populated or not) for this event type —
    # lets callers tell "some required fields blank" apart from "every
    # relevant required field blank" instead of treating any single blank
    # field as fatal to a section (see _tw_gate_should_skip).
    required_tw_fields: FrozenSet[str]
    rci_plan_sections: List[RciSectionItem]
    task_critique: List[TaskAssignmentItem]
    accepted_rc_conclusion: AcceptedRCConclusion
    accepted_capa: AcceptedCAPAProposal
    mc_confirmed: Optional[bool]
    history_lookback_months: int
    manual_entries: Dict[str, str]
    # The uploaded RC & CAPA document's own verbatim text (extract_rci_report_sections, no
    # LLM) — not a raw TrackWise audit-log field, so no strip_audit_log_prefix needed. Empty
    # string (not None) when no RC & CAPA document has been uploaded yet.
    uploaded_impact_assessment_text: str
    uploaded_correction_remedial_text: str
    uploaded_impact_conclusion_text: str

    def tw(self, key: str, default: str = "") -> str:
        value = self.trackwise_fields.get(key)
        return str(value) if value not in (None, "") else default

    def effectiveness_plan_evidence_text(self, capa_item: CAPAItemDetail) -> str:
        """Evidence for ONE row of Section 11 (CAPA Effectiveness Check Plan),
        scoped to exactly one accepted CAPA action — never capa_overall_text
        (a whole-proposal summary, not scoped to any one action; including it
        previously bled every other action's content back into a supposedly
        single-item plan, found and fixed 2026-08-06).

        Deliberately does NOT reuse capa_depth_effectiveness's evidence
        contract (a redacted copy of an already-completed report) — rci_report
        never has a completed report to read, so this is built entirely from
        upstream artifacts this module actually has: the accepted RC
        conclusion, this one CAPA action, and named individuals from
        TrackWise (deviation_owner/observed_by) for the responsibility field,
        which the CAPA action's own `responsibility` is often just a
        department, not a person (2026-08-06 finding).
        """
        named_individuals = "\n".join(
            filter(None, [
                f"Deviation Owner: {self.tw('deviation_owner')}" if self.tw("deviation_owner") else None,
                f"Observed By: {self.tw('observed_by')}" if self.tw("observed_by") else None,
                f"Analyst Name: {self.tw('analyst_name')}" if self.tw("analyst_name") else None,
            ])
        ) or "(none stated)"
        return (
            f"Root Cause Conclusion:\n{self.accepted_rc_conclusion.rc_conclusion_text}\n\n"
            f"This CAPA Action:\n- {capa_item.description} "
            f"(responsibility: {capa_item.responsibility or 'not stated'}, "
            f"due: {capa_item.due_date or 'not stated'})\n\n"
            f"Named Individuals (from TrackWise, for responsibility if the CAPA action "
            f"itself only states a department):\n{named_individuals}"
        )


def build_report_context(request: RciReportGenerationRequest) -> RciReportContext:
    """Pure, synchronous — no I/O. Called once at the top of the route, before
    any asyncio.gather wave."""
    return RciReportContext(
        event_type=request.event_type,
        deviation_id=request.deviation_id,
        trackwise_fields=request.trackwise_fields,
        missing_required_tw_fields=frozenset(
            missing_required_trackwise_fields(
                event_type=request.event_type,
                normalised_fields=request.trackwise_fields,
                event_functionality="rci_report",
            )
        ),
        required_tw_fields=frozenset(
            required_trackwise_fields(event_type=request.event_type, event_functionality="rci_report")
        ),
        rci_plan_sections=request.rci_plan_sections,
        task_critique=request.task_critique,
        accepted_rc_conclusion=request.accepted_rc_conclusion,
        accepted_capa=request.accepted_capa,
        mc_confirmed=request.mc_confirmed,
        history_lookback_months=request.history_lookback_months,
        manual_entries=request.manual_entries,
        uploaded_impact_assessment_text=(request.uploaded_impact_assessment_text or "").strip(),
        uploaded_correction_remedial_text=(request.uploaded_correction_remedial_text or "").strip(),
        uploaded_impact_conclusion_text=(request.uploaded_impact_conclusion_text or "").strip(),
    )
