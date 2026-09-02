"""
Regression tests for rci_report's schema validators and pure-logic services.

GAPS.md (src/agents/rci_report/GAPS.md, 2026-08-25 entry) explicitly notes that
despite many entries referencing a `test_rci_report.py` regression suite, no such
file actually existed — every one of these validators/deterministic computations
was live-validated by hand against real records but never covered by an automated
test. This file closes that gap for the schema validators and pure functions;
LLM-driven route behavior is out of scope here (see test_capa_depth_effectiveness.py
for the monkeypatch pattern this module would use if that coverage is added later).
"""

import pytest
from pydantic import ValidationError

from src.agents.rci_report.api.schemas.common import (
    CAPAExtrapolationItem,
    SourcedText,
)
from src.agents.rci_report.api.schemas.define import EquipmentActionChecklist
from src.agents.rci_report.api.schemas.improve_control import (
    CAPAActionItem,
    CAPAEffectivenessCheckPlanSection,
    CAPAEffectivenessPlanItem,
    CAPASection,
    CorrectionRemedialActionSection,
    ObservationStatusItem,
)
from src.agents.rci_report.api.schemas.measure_analyze import (
    HistoryReviewRow,
    HistoryReviewSection,
    ImpactAssessmentBatchDispositionSection,
    ImpactOnAffectedBatchSubsection,
    ImpactSubsection,
    InvestigationTaskSection,
    InvestigationTaskSummarySection,
    RootCauseIdentificationSection,
    RootCauseTaskLink,
    TaskSummaryItem,
    WhyWhyAnalysisSection,
    WhyWhyStep,
)
from src.agents.rci_report.api.services.history_review_service import (
    _rows_from_search_results,
)
from src.agents.rci_report.api.services.risk_scoring import (
    build_risk_assessment_section,
)
from src.agents.rci_report.api.services.text_cleaning import strip_audit_log_prefix
from src.agents.rci_report.api.services.risk_scoring import score_rpn
from src.agents.rci_report.api.schemas.measure_analyze import GeneratedRiskFactors, RiskFactorScores
from src.agents.rci_report.api.schemas.measure_analyze import (
    SeveritySelection,
    RepeatabilitySelection,
    DetectabilitySelection,
)


# ---------------------------------------------------------------------------
# common.py
# ---------------------------------------------------------------------------


def test_sourced_text_rejects_off_vocabulary_source():
    """See GAPS.md 2026-08-09 #2: source was a free str, so nothing stopped a
    typo'd/off-vocabulary value (e.g. capitalized 'TrackWise') from silently
    passing through and breaking downstream logic keyed on this field."""
    with pytest.raises(ValidationError):
        SourcedText(value="some value", source="TrackWise")


def test_sourced_text_accepts_each_literal_value():
    for source in ("trackwise", "manual_entry_required", "manual_entry_provided", "synthesized"):
        SourcedText(value="x", source=source)


def test_capa_extrapolation_not_applicable_requires_justification():
    with pytest.raises(ValidationError):
        CAPAExtrapolationItem(
            applicable=False,
            justification="",
            scope_description="",
            responsibility="",
            due_date="",
        )


def test_capa_extrapolation_not_applicable_with_justification_is_allowed():
    item = CAPAExtrapolationItem(
        applicable=False,
        justification="No extrapolation warranted — single-batch, isolated event.",
        scope_description="",
        responsibility="",
        due_date="",
    )
    assert item.applicable is False


def test_capa_extrapolation_applicable_true_needs_no_justification():
    item = CAPAExtrapolationItem(
        applicable=True,
        justification="",
        scope_description="all HDPE containers used for material storage",
        responsibility="QA",
        due_date="30/09/2026",
    )
    assert item.applicable is True


# ---------------------------------------------------------------------------
# define.py
# ---------------------------------------------------------------------------


def test_equipment_checklist_other_action_true_requires_specify():
    with pytest.raises(ValidationError):
        EquipmentActionChecklist(
            operation_suspended=True,
            on_hold_label_affixed=False,
            other_action_taken=True,
            other_action_specify="",
        )


def test_equipment_checklist_specify_without_other_action_is_rejected():
    with pytest.raises(ValidationError):
        EquipmentActionChecklist(
            operation_suspended=True,
            on_hold_label_affixed=False,
            other_action_taken=False,
            other_action_specify="Quarantined the batch manually.",
        )


def test_equipment_checklist_consistent_states_are_allowed():
    EquipmentActionChecklist(
        operation_suspended=True,
        on_hold_label_affixed=True,
        other_action_taken=False,
        other_action_specify="",
    )
    EquipmentActionChecklist(
        operation_suspended=False,
        on_hold_label_affixed=False,
        other_action_taken=True,
        other_action_specify="Segregated the entire SFG under quarantine.",
    )


# ---------------------------------------------------------------------------
# measure_analyze.py — HistoryReviewSection
# ---------------------------------------------------------------------------


def _history_row(event_number="DEV001") -> HistoryReviewRow:
    return HistoryReviewRow(
        event_number=event_number,
        event_title="Foreign object in tablet",
        capa_description="Line clearance SOP revised",
        capa_implementation_date="2026-01-15",
    )


def test_history_review_no_similar_events_with_rows_is_rejected():
    with pytest.raises(ValidationError):
        HistoryReviewSection(
            lookback_months=6,
            search_scope_note="test scope",
            rows=[_history_row()],
            no_similar_events_found=True,
            closing_narrative="No prior CAPA found.",
        )


def test_history_review_no_similar_events_with_empty_rows_is_allowed():
    section = HistoryReviewSection(
        lookback_months=6,
        search_scope_note="test scope",
        rows=[],
        no_similar_events_found=True,
        closing_narrative="No similar historical events found.",
    )
    assert section.rows == []


def test_history_review_rows_present_and_flag_false_is_allowed():
    section = HistoryReviewSection(
        lookback_months=6,
        search_scope_note="test scope",
        rows=[_history_row()],
        no_similar_events_found=False,
        closing_narrative="Prior CAPA appears effective.",
    )
    assert len(section.rows) == 1


# ---------------------------------------------------------------------------
# measure_analyze.py — WhyWhyAnalysisSection (the only RCA method rendered)
# ---------------------------------------------------------------------------


def test_why_why_analysis_requires_non_empty_chain():
    """Fishbone/Fault Tree/Flowchart were dropped entirely (2026-09-01, per
    the user) — Why-Why Analysis is the only RCA demonstration this section
    ever produces, so an empty chain is rejected outright rather than
    allowed as one of several possible methods."""
    with pytest.raises(ValidationError):
        WhyWhyAnalysisSection(
            six_m_factor="Method",
            method_rationale="The conclusion's own reasoning is a causal chain.",
            why_why_chain=[],
        )


def test_why_why_analysis_round_trips():
    demo = WhyWhyAnalysisSection(
        six_m_factor="Method",
        method_rationale="The accepted conclusion traces a single causal chain.",
        why_why_chain=[WhyWhyStep(question="Why did the deviation occur?", answer="SOP step was skipped.")],
    )
    assert demo.six_m_factor == "Method"
    assert demo.why_why_chain[0].question == "Why did the deviation occur?"


# ---------------------------------------------------------------------------
# measure_analyze.py — InvestigationTaskSection (non-Latin-script guard)
# ---------------------------------------------------------------------------


def _investigation_task_section(overview: str) -> InvestigationTaskSection:
    return InvestigationTaskSection(
        task_summary=InvestigationTaskSummarySection(
            overview=overview,
            tasks=[
                TaskSummaryItem(
                    tick="1.1", title="Verify dispensing SOP", six_m_factor="Method", outcome="No deviation found."
                )
            ],
        ),
        why_why_analysis=WhyWhyAnalysisSection(
            six_m_factor="Method",
            method_rationale="Linear causal chain in the conclusion.",
            why_why_chain=[WhyWhyStep(question="Why did the deviation occur?", answer="SOP step was skipped.")],
        ),
        root_cause_identification=RootCauseIdentificationSection(
            grounding_evidence="Task 1.1 supports the accepted conclusion.",
            applicable_tasks=[
                RootCauseTaskLink(
                    tick="1.1", title="Verify dispensing SOP", six_m_factor="Method", explanation="Matches conclusion."
                )
            ],
        ),
    )


def test_investigation_task_rejects_non_latin_characters():
    """See GAPS.md 2026-08-06 #1: a stray CJK character was found mid-sentence in
    real generated output ('a现场/GEMBA-style shop-floor walk')."""
    with pytest.raises(ValidationError):
        _investigation_task_section("a现场/GEMBA-style shop-floor walk was conducted.")


def test_investigation_task_allows_ordinary_english_text():
    section = _investigation_task_section("A GEMBA-style shop-floor walk was conducted across all tasks.")
    assert "GEMBA" in section.task_summary.overview


# ---------------------------------------------------------------------------
# measure_analyze.py — ImpactAssessmentBatchDispositionSection
# ---------------------------------------------------------------------------


def _impact_section(**overrides) -> ImpactAssessmentBatchDispositionSection:
    defaults = dict(
        impact_on_affected_batches=ImpactOnAffectedBatchSubsection(applicable=True, narrative="Batch verified."),
        impact_on_marketed_released_batches=ImpactSubsection(applicable=False, narrative="NA"),
        impact_on_other_product_material_area_process=ImpactSubsection(applicable=False, narrative="NA"),
        impact_on_regulatory_filing=ImpactSubsection(applicable=False, narrative="NA"),
        impact_on_facility_equipment_instrument=ImpactSubsection(applicable=False, narrative="NA"),
        impact_on_manufacturing_process_analytical_method=ImpactSubsection(applicable=False, narrative="NA"),
        business_continuity=ImpactSubsection(applicable=False, narrative="NA"),
        impact_on_data_integrity=ImpactSubsection(applicable=False, narrative="NA"),
        stability_repackaging_requirement=ImpactSubsection(applicable=False, narrative="NA"),
        patient_safety=ImpactSubsection(applicable=True, narrative="No patient safety impact identified beyond scope."),
        others_as_applicable=ImpactSubsection(applicable=False, narrative="NA"),
        conclusion="No further impact identified.",
    )
    defaults.update(overrides)
    return ImpactAssessmentBatchDispositionSection(**defaults)


def test_impact_section_others_verbatim_duplicate_of_patient_safety_is_rejected():
    with pytest.raises(ValidationError):
        _impact_section(
            others_as_applicable=ImpactSubsection(applicable=True, narrative="Same bullet text as patient safety."),
            patient_safety=ImpactSubsection(applicable=True, narrative="Same bullet text as patient safety."),
        )


def test_impact_section_distinct_others_and_patient_safety_is_allowed():
    section = _impact_section(
        others_as_applicable=ImpactSubsection(applicable=True, narrative="Distinct regulatory notification impact."),
    )
    assert section.others_as_applicable.applicable is True


@pytest.mark.parametrize(
    "field_name",
    [
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
    ],
)
def test_impact_section_applicable_true_with_na_narrative_is_rejected(field_name):
    """See GAPS.md 2026-08-06: applicable=True paired with an 'NA'-prefixed
    narrative is a self-contradictory pairing found live across several
    subsections, not just one — the validator must catch it on every subsection."""
    kwargs = {field_name: ImpactSubsection(applicable=True, narrative="NA — no impact identified as a contributing factor.")}
    if field_name == "impact_on_affected_batches":
        kwargs[field_name] = ImpactOnAffectedBatchSubsection(
            applicable=True, narrative="NA — no impact identified as a contributing factor."
        )
    with pytest.raises(ValidationError):
        _impact_section(**kwargs)


def test_impact_section_applicable_false_with_na_narrative_is_allowed():
    section = _impact_section()
    assert section.impact_on_regulatory_filing.applicable is False


# ---------------------------------------------------------------------------
# improve_control.py — CorrectionRemedialActionSection
# ---------------------------------------------------------------------------


def test_correction_remedial_fully_blank_is_rejected():
    """See GAPS.md 2026-08-09 #8: unlike CAPA/Risk Assessment, this section has
    no 'not applicable' escape valve — an entirely empty result is never
    legitimate for a real event."""
    with pytest.raises(ValidationError):
        CorrectionRemedialActionSection(items=[], additional_notes=[])


def test_correction_remedial_with_items_only_is_allowed():
    section = CorrectionRemedialActionSection(
        items=[ObservationStatusItem(observation="Cable replaced.", status="Replaced with new cable.")],
        additional_notes=[],
    )
    assert len(section.items) == 1


def test_correction_remedial_with_notes_only_is_allowed():
    section = CorrectionRemedialActionSection(items=[], additional_notes=["No corrective action was required."])
    assert section.additional_notes


def test_observation_status_item_keeps_reference_embedded_in_status():
    """See GAPS.md 2026-08-09 #8: status keeps the reference number embedded
    verbatim (matches real-report rendering); reference_number is additive,
    not extracted out of status."""
    item = ObservationStatusItem(
        observation="Container replaced.",
        status="SAP notification#10243982 initiated for the replacement.",
        reference_number="10243982",
    )
    assert "10243982" in item.status
    assert item.reference_number == "10243982"


# ---------------------------------------------------------------------------
# improve_control.py — CAPASection
# ---------------------------------------------------------------------------


def _capa_extrapolation_not_applicable() -> CAPAExtrapolationItem:
    return CAPAExtrapolationItem(
        applicable=False,
        justification="Single isolated event — no extrapolation warranted.",
        scope_description="",
        responsibility="",
        due_date="",
    )


def test_capa_section_justification_and_actions_together_is_rejected():
    with pytest.raises(ValidationError):
        CAPASection(
            capa_not_applicable_justification="No CAPA is warranted.",
            capa_actions=[CAPAActionItem(description="Revise SOP.", due_date="30/09/2026")],
            interim_controls=[],
            extrapolation=_capa_extrapolation_not_applicable(),
        )


def test_capa_section_neither_justification_nor_actions_is_rejected():
    """See GAPS.md 2026-08-09 #9: the original validator only guarded the
    simultaneous case — a silently blank CAPA section previously passed."""
    with pytest.raises(ValidationError):
        CAPASection(
            capa_not_applicable_justification=None,
            capa_actions=[],
            interim_controls=[],
            extrapolation=_capa_extrapolation_not_applicable(),
        )


def test_capa_section_actions_only_is_allowed():
    section = CAPASection(
        capa_not_applicable_justification=None,
        capa_actions=[CAPAActionItem(description="Revise SOP F1/PR/003.", due_date="30/09/2026")],
        interim_controls=[],
        extrapolation=_capa_extrapolation_not_applicable(),
    )
    assert section.capa_actions[0].responsibility is None


def test_capa_action_item_responsibility_is_optional():
    """See GAPS.md 2026-08-09 #9: the real Market Complaint report's CAPA table
    has no Responsibility column at all — forcing this field required made the
    model fabricate a value."""
    item = CAPAActionItem(description="Replace containers.", due_date="Completed")
    assert item.responsibility is None


# ---------------------------------------------------------------------------
# improve_control.py — CAPAEffectivenessCheckPlanSection
# ---------------------------------------------------------------------------


def _effectiveness_plan_item(**overrides) -> CAPAEffectivenessPlanItem:
    defaults = dict(
        grounding_evidence="Procedural fix tied to a training gap.",
        capa_mechanism="Procedural / training-based",
        capa_description="Revise SOP F1/PR/003 and retrain line operators.",
        effectiveness_check=["Verify training completion.", "Observe 5 line-clearance activities."],
        effectiveness_criteria=["Zero missed line-clearance steps across the monitoring window."],
        responsibility="R Anand",
        duration_rationale="Procedural fix — standard monitoring window.",
        duration_tier="standard",
        monitoring_duration="10 batches or 90 days, whichever is earlier",
    )
    defaults.update(overrides)
    return CAPAEffectivenessPlanItem(**defaults)


def test_effectiveness_plan_justification_and_plans_together_is_rejected():
    with pytest.raises(ValidationError):
        CAPAEffectivenessCheckPlanSection(
            capa_not_applicable_justification="No CAPA is warranted.",
            generated_plans=[_effectiveness_plan_item()],
        )


def test_effectiveness_plan_neither_justification_nor_plans_is_rejected():
    with pytest.raises(ValidationError):
        CAPAEffectivenessCheckPlanSection(capa_not_applicable_justification=None, generated_plans=[])


def test_effectiveness_plan_one_row_per_capa_action_is_allowed():
    """See GAPS.md 2026-08-06: the real production UI renders one row per
    accepted CAPA action, not one consolidated row."""
    section = CAPAEffectivenessCheckPlanSection(
        capa_not_applicable_justification=None,
        generated_plans=[
            _effectiveness_plan_item(capa_description="Revise SOP F1/PR/003."),
            _effectiveness_plan_item(capa_description="Replace with scratch-proof containers.", capa_mechanism="Resource / equipment substitution"),
        ],
    )
    assert len(section.generated_plans) == 2


# ---------------------------------------------------------------------------
# risk_scoring.py — score_rpn (pure function, deterministic RPN/band computation)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "severity,repeatability,detectability,expected_rpn,expected_level",
    [
        ("Low", "Low", "Low", 1, "L1"),
        ("Medium", "Low", "Low", 10, "L3"),
        ("Low", "Medium", "Low", 5, "L2"),
        ("Critical", "High", "High", 27 * 10 * 5, "L5"),
        ("Medium", "Medium", "Low", 50, "L4"),
    ],
)
def test_score_rpn_bands(severity, repeatability, detectability, expected_rpn, expected_level):
    _, _, _, rpn, risk_level = score_rpn(severity, repeatability, detectability)
    assert rpn == expected_rpn
    assert risk_level == expected_level


def test_score_rpn_band_boundaries():
    # rpn=9 -> L2 (just under the <10 boundary); rpn=10 -> L3 (>=10, <27)
    assert score_rpn("Low", "Medium", "Low")[3:] == (5, "L2")  # rpn = 1*5*1 = 5
    # Construct exact boundary values using the score tables directly.
    assert score_rpn("Medium", "Low", "Low")[3] == 10
    assert score_rpn("Medium", "Low", "Low")[4] == "L3"
    assert score_rpn("Critical", "Low", "Low")[3] == 27
    assert score_rpn("Critical", "Low", "Low")[4] == "L4"
    assert score_rpn("Critical", "High", "High")[3] == 1350
    assert score_rpn("Critical", "High", "High")[4] == "L5"


def test_build_risk_assessment_section_computes_scores_from_llm_tiers():
    generated = GeneratedRiskFactors(
        applicability_reason="A root cause and one probable cause were both identified.",
        applicable="yes",
        candidate_labels=["Root cause", "Probable cause 1"],
        candidates=[
            RiskFactorScores(
                severity=SeveritySelection(grounding_evidence="Patient-facing defect.", tier="Critical"),
                repeatability=RepeatabilitySelection(grounding_evidence="First occurrence.", tier="Low"),
                detectability=DetectabilitySelection(grounding_evidence="Caught at final inspection.", tier="High"),
            ),
            RiskFactorScores(
                severity=SeveritySelection(grounding_evidence="Minor cosmetic defect.", tier="Low"),
                repeatability=RepeatabilitySelection(grounding_evidence="Recurs frequently.", tier="High"),
                detectability=DetectabilitySelection(grounding_evidence="Hard to detect in-process.", tier="Low"),
            ),
        ],
    )
    section = build_risk_assessment_section(generated)
    assert len(section.candidates) == 2
    assert section.candidates[0].cause_label == "Root cause"
    assert section.candidates[0].rpn == 27 * 1 * 5
    assert section.candidates[0].risk_level == "L4"
    assert section.candidates[1].rpn == 1 * 10 * 1
    assert section.candidates[1].risk_level == "L3"


def test_generated_risk_factors_not_applicable_with_candidates_is_rejected():
    with pytest.raises(ValidationError):
        GeneratedRiskFactors(
            applicability_reason="Unconfirmed market complaint — no root cause assigned yet.",
            applicable="no — unconfirmed market complaint",
            candidate_labels=["Root cause"],
            candidates=[
                RiskFactorScores(
                    severity=SeveritySelection(grounding_evidence="x", tier="Low"),
                    repeatability=RepeatabilitySelection(grounding_evidence="x", tier="Low"),
                    detectability=DetectabilitySelection(grounding_evidence="x", tier="Low"),
                )
            ],
        )


def test_generated_risk_factors_applicable_yes_with_no_candidates_is_rejected():
    with pytest.raises(ValidationError):
        GeneratedRiskFactors(
            applicability_reason="A root cause was identified.",
            applicable="yes",
            candidate_labels=[],
            candidates=[],
        )


def test_generated_risk_factors_mismatched_label_and_candidate_counts_is_rejected():
    with pytest.raises(ValidationError):
        GeneratedRiskFactors(
            applicability_reason="A root cause was identified.",
            applicable="yes",
            candidate_labels=["Root cause", "Probable cause 1"],
            candidates=[
                RiskFactorScores(
                    severity=SeveritySelection(grounding_evidence="x", tier="Low"),
                    repeatability=RepeatabilitySelection(grounding_evidence="x", tier="Low"),
                    detectability=DetectabilitySelection(grounding_evidence="x", tier="Low"),
                )
            ],
        )


# ---------------------------------------------------------------------------
# text_cleaning.py — strip_audit_log_prefix
# ---------------------------------------------------------------------------


def test_strip_audit_log_prefix_removes_trackwise_metadata():
    text = (
        "10/31/2025 10:02 PM (GMT+5:30) added by R Anand (PID-008030): "
        "The container was replaced with a scratch-proof alternative."
    )
    assert strip_audit_log_prefix(text) == "The container was replaced with a scratch-proof alternative."


def test_strip_audit_log_prefix_leaves_plain_text_unchanged():
    text = "The container was replaced with a scratch-proof alternative."
    assert strip_audit_log_prefix(text) == text


def test_strip_audit_log_prefix_empty_string_returns_unchanged():
    assert strip_audit_log_prefix("") == ""


def test_strip_audit_log_prefix_strips_every_occurrence():
    text = (
        "10/31/2025 10:02 PM (GMT+5:30) added by R Anand (PID-008030): First entry. "
        "11/02/2025 9:15 AM (GMT+5:30) added by J Doe (PID-000123): Second entry."
    )
    assert strip_audit_log_prefix(text) == "First entry. Second entry."


# ---------------------------------------------------------------------------
# history_review_service.py — _rows_from_search_results (pure function)
# ---------------------------------------------------------------------------


def test_rows_from_search_results_hydrates_capa_columns_by_id(monkeypatch):
    from src.agents.rci_report.api.services import history_review_service as svc

    monkeypatch.setattr(svc.settings, "COLUMN_ID", "deviation_id")
    monkeypatch.setattr(svc.settings, "COLUMN_DESCRIPTION", "description", raising=False)

    candidates = [
        {"deviation_id": "DEV001", "title": "Foreign object in tablet"},
        {"deviation_id": "DEV002", "description": "Color variation in batch"},
    ]
    capa_by_id = {
        "DEV001": {"capa_description": "Line clearance SOP revised", "capa_implementation_date": "2026-01-15"},
    }

    rows = svc._rows_from_search_results(candidates, capa_by_id)

    assert len(rows) == 2
    assert rows[0].event_number == "DEV001"
    assert rows[0].event_title == "Foreign object in tablet"
    assert rows[0].capa_description == "Line clearance SOP revised"
    assert rows[1].event_number == "DEV002"
    assert rows[1].event_title == "Color variation in batch"
    assert rows[1].capa_description == ""  # no hydration entry for DEV002


def test_rows_from_search_results_empty_candidates_returns_empty_list():
    rows = _rows_from_search_results([], {})
    assert rows == []


# ---------------------------------------------------------------------------
# Endpoint-level test — POST /rci-report/generate, the real route end to end.
#
# 9 concurrent Wave-1 LLM calls (description_of_event, initial_impact_assessment,
# history_review, investigation_task, root_cause_conclusion,
# impact_assessment_batch_disposition, correction_remedial_action, capa,
# capa_effectiveness_check_plan) feed 2 Wave-2 calls (risk_assessment,
# executive_summary) that consume Wave-1's own output. LLMClient.get_structured_response
# is a single class method dispatched on its `structure=` kwarg (same pattern as
# test_capa_depth_effectiveness.py); History Review additionally routes through
# search_agent's build_search_graph, mocked separately so no real DB/search
# infra is needed. The request payload below was verified empirically (see
# build_report_context/_section_missing_deps) to leave every gated section
# (description_of_event, initial_impact_assessment, root_cause_conclusion,
# impact_assessment_batch_disposition, correction_remedial_action, capa)
# un-skipped, so all 11 response sections actually attempt generation.
# ---------------------------------------------------------------------------


from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.agents.app import create_app
from src.agents.critique.api.schemas import CAPAItemDetail
from src.agents.rci_report.api.schemas.define import (
    DescriptionOfEventSection,
    EquipmentActionChecklist as _EquipmentActionChecklist,
    EquipmentImpactItem,
    ExecutiveSummarySection,
    InitialImpactAssessmentSection,
    MaterialProductImpactItem,
)
from src.agents.rci_report.api.schemas.measure_analyze import RootCauseConclusionSection, RootCauseTaxonomy
from src.agents.rci_report.api.schemas.request import (
    AcceptedCAPAProposal,
    AcceptedRCConclusion,
    RciReportGenerationRequest,
)
from src.agents.rci_report.api.services.history_review_service import HistoryReviewNarrative
from src.utils import deps

rci_report_client = TestClient(create_app())


def _rci_report_request_payload():
    return {
        "event_type": "Deviation",
        "deviation_id": "DEV-2026-001",
        "trackwise_fields": {
            "title": "Blender speed deviation",
            "Batch Number / AR Number": "B-001",
            "Product / Material Code": "PMC-1",
            "Product Name / Material Name": "Product X",
            "Deviation To": "Process",
            "Equipment Name": "Blender",
            "description": "Blender ran outside the validated speed range during granulation.",
            "Instrument ID Number": "INS-1",
            "Name of the Instrument": "Blender A",
            "Observed By": "J Doe",
            "Deviation Number": "DEV-2026-001",
            "Date Opened": "2026-08-01",
            "Observation Date": "2026-08-01",
            "Observation Time": "10:00",
            "Failure Duration": "1 hour",
            "Equipment ID": "EQ-1",
            "Equipment Number": "EQN-1",
            "Deviation Owner": "J Doe",
            "Originator": "J Doe",
            "Impact on Deviation Batches": "None",
            "Immediate Cause Known": "Yes",
            "Cause Detail": "Operator error",
            "Impact Details": "No significant impact identified.",
        },
        "accepted_rc_conclusion": {
            "rc_conclusion_text": "Root cause was operator error in setting blender speed; SOP step was skipped.",
        },
        "accepted_capa": {
            "capa_items": [
                {"description": "Revise SOP F1/PR/003 and retrain operators.", "responsibility": "QA", "due_date": "30/09/2026"}
            ],
        },
        "uploaded_correction_remedial_text": "Cable was replaced with a scratch-proof alternative; line clearance performed.",
        "uploaded_impact_assessment_text": "No adverse impact on product quality was identified. Batch B-001 is released.",
    }


def _fake_description_of_event():
    return DescriptionOfEventSection(
        what_happened="Blender exceeded the validated speed range during granulation.",
        when_happened="On 01/08/2026 at 10:00 hrs.",
        who_identified="J Doe (Observed By)",
        where_it_happened="Granulation area, Blender A.",
        nonconforming_reference=SourcedText(value="Process deviation from validated range.", source="trackwise"),
        how_detected=SourcedText(value="In-process monitoring alarm.", source="trackwise"),
    )


def _fake_initial_impact_assessment():
    return InitialImpactAssessmentSection(
        material_product_impacts=[
            MaterialProductImpactItem(
                material_product_batch="Product X, batch B-001",
                stage="Granulation",
                quantity_involved="1 batch",
                quantity_on_hold=SourcedText(value="1 batch", source="trackwise"),
                type_of_impact="Direct",
            )
        ],
        equipment_impacts=[
            EquipmentImpactItem(
                equipment_instrument=SourcedText(value="Blender A", source="trackwise"),
                identification_number=SourcedText(value="EQ-1", source="trackwise"),
                actions_initiated=_EquipmentActionChecklist(
                    operation_suspended=True, on_hold_label_affixed=True, other_action_taken=False, other_action_specify=""
                ),
            )
        ],
        immediate_actions=["Batch placed on hold pending investigation."],
    )


def _fake_investigation_task():
    return InvestigationTaskSection(
        task_summary=InvestigationTaskSummarySection(
            overview="One task verified the blender speed control settings.",
            tasks=[
                TaskSummaryItem(
                    tick="1.1", title="Verify blender speed control settings", six_m_factor="Machine",
                    outcome="Speed control setpoint was found incorrectly configured.",
                )
            ],
        ),
        why_why_analysis=WhyWhyAnalysisSection(
            six_m_factor="Machine",
            method_rationale="The conclusion describes a single linear causal chain.",
            why_why_chain=[WhyWhyStep(question="Why did the blender exceed speed range?", answer="The setpoint was misconfigured.")],
        ),
        root_cause_identification=RootCauseIdentificationSection(
            grounding_evidence="Task 1.1 directly supports the accepted conclusion.",
            applicable_tasks=[
                RootCauseTaskLink(
                    tick="1.1", title="Verify blender speed control settings", six_m_factor="Machine",
                    explanation="Confirms the speed setpoint error described in the accepted conclusion.",
                )
            ],
        ),
    )


def _fake_root_cause_conclusion():
    return RootCauseConclusionSection(
        conclusion="Blender speed setpoint was misconfigured, causing an out-of-range run.",
        taxonomy=RootCauseTaxonomy(category="Machine", sub_category="Incorrect equipment setpoint"),
        repeat_occurrence_evidence="No prior similar events found in History Review.",
        is_repeat_occurrence=False,
    )


def _fake_impact_assessment_batch_disposition():
    na = ImpactSubsection(applicable=False, narrative="NA")
    return ImpactAssessmentBatchDispositionSection(
        impact_on_affected_batches=ImpactOnAffectedBatchSubsection(applicable=True, narrative="Batch B-001 placed on hold."),
        impact_on_marketed_released_batches=na,
        impact_on_other_product_material_area_process=na,
        impact_on_regulatory_filing=na,
        impact_on_facility_equipment_instrument=na,
        impact_on_manufacturing_process_analytical_method=na,
        business_continuity=na,
        impact_on_data_integrity=na,
        stability_repackaging_requirement=na,
        patient_safety=na,
        others_as_applicable=na,
        conclusion="No further impact identified beyond the affected batch.",
    )


def _fake_correction_remedial_action():
    return CorrectionRemedialActionSection(
        items=[ObservationStatusItem(observation="Speed control cable replaced.", status="Replaced with new cable.")],
    )


def _fake_capa():
    return CAPASection(
        capa_actions=[CAPAActionItem(description="Revise SOP F1/PR/003 and retrain operators.", responsibility="QA", due_date="30/09/2026")],
        extrapolation=CAPAExtrapolationItem(
            applicable=False, justification="Single isolated event.", scope_description="", responsibility="", due_date="",
        ),
    )


def _fake_capa_effectiveness_plan_item():
    return CAPAEffectivenessPlanItem(
        grounding_evidence="Procedural fix tied to an operator training gap.",
        capa_mechanism="Procedural / training-based",
        capa_description="Revise SOP F1/PR/003 and retrain operators.",
        effectiveness_check=["Verify training completion.", "Observe blender startup procedure for 5 batches."],
        effectiveness_criteria=["Zero speed-range deviations across the monitoring window."],
        responsibility="J Doe",
        duration_rationale="Procedural fix — standard monitoring window.",
        duration_tier="standard",
        monitoring_duration="10 batches or 90 days, whichever is earlier",
    )


def _fake_risk_factors():
    return GeneratedRiskFactors(
        applicability_reason="Not a Market Complaint — risk assessment applies normally.",
        applicable="no — unconfirmed market complaint",
        candidate_labels=[],
        candidates=[],
    )


def _fake_executive_summary():
    return ExecutiveSummarySection(
        summary="Blender speed setpoint error caused an out-of-range granulation run.",
        problem_description="Blender exceeded its validated speed range during granulation.",
        immediate_containment_action="Batch B-001 was placed on hold.",
        determination_of_root_cause="Investigation traced the deviation to a misconfigured speed setpoint.",
        root_cause_probable_cause_statement="Incorrect blender speed setpoint.",
        impact_assessment="Limited to the one affected batch, which was placed on hold.",
        correction_conclusion_preventive_actions="SOP revised and operators retrained; cable replaced.",
        conclusion_statement="Batch B-001 disposition pending CAPA closure.",
    )


def _fake_get_structured_response(structure):
    if structure is DescriptionOfEventSection:
        return _fake_description_of_event()
    if structure is InitialImpactAssessmentSection:
        return _fake_initial_impact_assessment()
    if structure is InvestigationTaskSection:
        return _fake_investigation_task()
    if structure is RootCauseConclusionSection:
        return _fake_root_cause_conclusion()
    if structure is ImpactAssessmentBatchDispositionSection:
        return _fake_impact_assessment_batch_disposition()
    if structure is CorrectionRemedialActionSection:
        return _fake_correction_remedial_action()
    if structure is CAPASection:
        return _fake_capa()
    if structure is CAPAEffectivenessPlanItem:
        return _fake_capa_effectiveness_plan_item()
    if structure is GeneratedRiskFactors:
        return _fake_risk_factors()
    if structure is ExecutiveSummarySection:
        return _fake_executive_summary()
    if structure is HistoryReviewNarrative:
        return HistoryReviewNarrative(closing_narrative="No similar historical events found; no prior CAPA to assess.")
    raise AssertionError(f"Unexpected structure requested: {structure}")


@pytest.fixture(autouse=True)
def _reset_rci_report_deps():
    yield
    deps._pool = None
    deps._llm = None
    deps._prompt_registry = None


def test_generate_rci_report_all_sections_succeed(monkeypatch):
    """End-to-end: real route, real graph-free orchestration (asyncio.gather
    over the 9 Wave-1 + 2 Wave-2 generators), only the LLM boundary and
    History Review's search-graph dependency mocked. Confirms none of the 6
    TrackWise/API-gated sections are skipped and every response field is
    populated — not just that the route returns 200."""

    async def fake_get_structured_response(self, user_prompt, structure, system_prompt=None, temperature=None):
        return _fake_get_structured_response(structure)

    monkeypatch.setattr("src.llm.client.LLMClient.get_structured_response", fake_get_structured_response)
    monkeypatch.setattr(
        "src.agents.rci_report.api.services.history_review_service.build_search_graph",
        lambda **kwargs: MagicMock(ainvoke=AsyncMock(return_value={"final_results": []})),
    )
    deps.set_pool(MagicMock())

    response = rci_report_client.post("/rci-report/generate", json=_rci_report_request_payload())

    assert response.status_code == 200
    data = response.json()

    assert data["errors"] == {}
    assert data["event_type"] == "Deviation"
    for section in (
        "executive_summary", "description_of_event", "initial_impact_assessment", "history_review",
        "investigation_task", "root_cause_conclusion", "impact_assessment_batch_disposition",
        "risk_assessment", "correction_remedial_action", "capa", "capa_effectiveness_check_plan",
    ):
        assert data[section] is not None, f"{section} unexpectedly None: errors={data['errors']}"

    assert data["history_review"]["no_similar_events_found"] is True
    assert data["history_review"]["closing_narrative"]
    assert data["capa_effectiveness_check_plan"]["generated_plans"][0]["capa_description"] == (
        "Revise SOP F1/PR/003 and retrain operators."
    )
    assert data["risk_assessment"]["applicable"] == "no — unconfirmed market complaint"
    assert data["executive_summary"]["summary"]


def test_generate_rci_report_investigation_task_no_evidence_marker(monkeypatch):
    """2026-09-01, per the user: a task with no Task Critique evidence at all (critique
    is null/blank) must have its outcome overridden with an explicit "no evidence"
    marker, regardless of whatever outcome _fake_investigation_task() (the mocked LLM
    response) wrote for that tick — the override in _generate_investigation_task is
    deterministic, not dependent on the LLM having followed the prompt's instruction."""

    async def fake_get_structured_response(self, user_prompt, structure, system_prompt=None, temperature=None):
        return _fake_get_structured_response(structure)

    monkeypatch.setattr("src.llm.client.LLMClient.get_structured_response", fake_get_structured_response)
    monkeypatch.setattr(
        "src.agents.rci_report.api.services.history_review_service.build_search_graph",
        lambda **kwargs: MagicMock(ainvoke=AsyncMock(return_value={"final_results": []})),
    )
    deps.set_pool(MagicMock())

    payload = _rci_report_request_payload()
    # tick "1.1" matches _fake_investigation_task()'s own single task, whose fake
    # outcome ("Speed control setpoint was found incorrectly configured.") must be
    # discarded and replaced since this task's critique is blank here.
    payload["task_critique"] = [
        {
            "tick": "1.1", "task": "Verify blender speed control settings",
            "responsible_person": "QA", "selected": True, "critique": None, "mandatory": True,
        }
    ]

    response = rci_report_client.post("/rci-report/generate", json=payload)

    assert response.status_code == 200
    data = response.json()
    task = data["investigation_task"]["task_summary"]["tasks"][0]
    assert task["tick"] == "1.1"
    assert task["outcome"] == (
        "No Task Critique evidence was available for this task — outcome could not be established."
    )
    assert task["outcome"] != "Speed control setpoint was found incorrectly configured."


def test_generate_rci_report_impact_conclusion_sourced_verbatim_from_upload(monkeypatch):
    """2026-09-01, per the user: when the uploaded RC & CAPA document states its own
    batch-disposition conclusion, Section 7's `conclusion` is that verbatim text, not
    the LLM-drafted one _fake_impact_assessment_batch_disposition() returns for every
    other field in this section."""

    async def fake_get_structured_response(self, user_prompt, structure, system_prompt=None, temperature=None):
        return _fake_get_structured_response(structure)

    monkeypatch.setattr("src.llm.client.LLMClient.get_structured_response", fake_get_structured_response)
    monkeypatch.setattr(
        "src.agents.rci_report.api.services.history_review_service.build_search_graph",
        lambda **kwargs: MagicMock(ainvoke=AsyncMock(return_value={"final_results": []})),
    )
    deps.set_pool(MagicMock())

    payload = _rci_report_request_payload()
    payload["uploaded_impact_conclusion_text"] = "Batch B-001 is released; no further action required."

    response = rci_report_client.post("/rci-report/generate", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["impact_assessment_batch_disposition"]["conclusion"] == (
        "Batch B-001 is released; no further action required."
    )
    # The other 11 subsections are untouched — still the LLM-drafted fake.
    assert data["impact_assessment_batch_disposition"]["impact_on_affected_batches"]["narrative"] == (
        "Batch B-001 placed on hold."
    )


def test_generate_rci_report_impact_conclusion_never_llm_synthesized_when_not_uploaded(monkeypatch):
    """2026-09-01, per the user: no uploaded_impact_conclusion_text (e.g. no RC & CAPA
    document uploaded yet, or no explicit conclusion line found in it) must NEVER fall
    back to the LLM's own drafted conclusion — that field is always overridden with an
    explicit "not stated" note instead, even though _fake_impact_assessment_batch_
    disposition() (the mocked LLM response) still returns its own conclusion text for
    this field, confirming the route discards it unconditionally."""

    async def fake_get_structured_response(self, user_prompt, structure, system_prompt=None, temperature=None):
        return _fake_get_structured_response(structure)

    monkeypatch.setattr("src.llm.client.LLMClient.get_structured_response", fake_get_structured_response)
    monkeypatch.setattr(
        "src.agents.rci_report.api.services.history_review_service.build_search_graph",
        lambda **kwargs: MagicMock(ainvoke=AsyncMock(return_value={"final_results": []})),
    )
    deps.set_pool(MagicMock())

    response = rci_report_client.post("/rci-report/generate", json=_rci_report_request_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["impact_assessment_batch_disposition"]["conclusion"] == (
        "Not stated in the uploaded RC & CAPA document."
    )
    assert data["impact_assessment_batch_disposition"]["conclusion"] != (
        "No further impact identified beyond the affected batch."
    )


def test_generate_rci_report_blank_rc_conclusion_skips_dependent_sections(monkeypatch):
    """A blank accepted_rc_conclusion.rc_conclusion_text must skip
    root_cause_conclusion AND impact_assessment_batch_disposition (both
    sole-sourced from it — see _section_missing_deps), which in turn skips
    risk_assessment (depends on both) by dependency — without crashing the
    rest of the report."""

    async def fake_get_structured_response(self, user_prompt, structure, system_prompt=None, temperature=None):
        return _fake_get_structured_response(structure)

    monkeypatch.setattr("src.llm.client.LLMClient.get_structured_response", fake_get_structured_response)
    monkeypatch.setattr(
        "src.agents.rci_report.api.services.history_review_service.build_search_graph",
        lambda **kwargs: MagicMock(ainvoke=AsyncMock(return_value={"final_results": []})),
    )
    deps.set_pool(MagicMock())

    payload = _rci_report_request_payload()
    payload["accepted_rc_conclusion"] = {"rc_conclusion_text": ""}

    response = rci_report_client.post("/rci-report/generate", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert data["root_cause_conclusion"] is None
    assert data["impact_assessment_batch_disposition"] is None
    assert data["risk_assessment"] is None
    assert "skipped" in data["errors"]["root_cause_conclusion"].lower()
    assert "skipped" in data["errors"]["impact_assessment_batch_disposition"].lower()
    assert "root cause" in data["errors"]["risk_assessment"].lower() or "impact assessment" in data["errors"]["risk_assessment"].lower()
    # Unrelated sections must still succeed — one section's gate must not sink the report.
    assert data["description_of_event"] is not None
    assert data["capa"] is not None


def test_generate_rci_report_blank_impact_assessment_text_skips_section(monkeypatch):
    """2026-09-01, per the user: Impact Assessment & Batch Disposition no longer
    falls back to TrackWise fields at all — it's sole-sourced from the uploaded
    RC & CAPA document's own Impact Assessment text, same pattern as
    Correction/Remedial Action. A blank uploaded_impact_assessment_text must
    skip it (and risk_assessment by dependency) even when accepted_rc_conclusion
    is populated."""

    async def fake_get_structured_response(self, user_prompt, structure, system_prompt=None, temperature=None):
        return _fake_get_structured_response(structure)

    monkeypatch.setattr("src.llm.client.LLMClient.get_structured_response", fake_get_structured_response)
    monkeypatch.setattr(
        "src.agents.rci_report.api.services.history_review_service.build_search_graph",
        lambda **kwargs: MagicMock(ainvoke=AsyncMock(return_value={"final_results": []})),
    )
    deps.set_pool(MagicMock())

    payload = _rci_report_request_payload()
    payload["uploaded_impact_assessment_text"] = None

    response = rci_report_client.post("/rci-report/generate", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert data["impact_assessment_batch_disposition"] is None
    assert data["risk_assessment"] is None
    assert "skipped" in data["errors"]["impact_assessment_batch_disposition"].lower()
    # root_cause_conclusion is independent of uploaded_impact_assessment_text — must still succeed.
    assert data["root_cause_conclusion"] is not None
