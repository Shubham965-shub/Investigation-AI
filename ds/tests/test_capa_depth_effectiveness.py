from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.agents.app import create_app
from src.agents.capa_depth_effectiveness.api.schemas import (
    CAPAActionClassification,
    CAPADepthClassification,
    CritiqueReasoning,
    EffectivenessCheckExtraction,
    EffectivenessCheckExtractionAndCritique,
    EffectivenessCheckRuleCritiques,
    EffectivenessPlanGrounding,
    ExtractionReasoning,
    GeneratedEffectivenessPlan,
    RuleCritique,
)
from src.agents.capa_depth_effectiveness.api.services.capa_depth_effectiveness_service import (
    call_with_retry,
    strip_section_12,
)
from src.prompt_registry.service import PromptRegistry
from src.utils import deps

# The route now loads its system prompts from PromptRegistry at request time
# (migrated off static .txt files, 2026-09-02) — client is built directly
# rather than as a lifespan-entering context manager, so the registry that
# lifespan would normally set up is registered explicitly here instead.
# Must be a per-test fixture, not bare module-level code: deps._prompt_registry
# is a process-global, and other test files' fixtures (e.g.
# test_problem_statement_evaluation_v2.py) reset it to None in their own
# teardown — a one-time module-level set gets wiped out by the time this
# file's tests actually run later in a full-suite session.
@pytest.fixture(autouse=True)
def _prompt_registry():
    deps.set_prompt_registry(PromptRegistry())
    yield
    deps._prompt_registry = None

client = TestClient(create_app())

ROUTE_MODULE = "src.agents.capa_depth_effectiveness.api.routes.capa_depth_effectiveness_route"


def test_strip_section_12_removes_real_content():
    """The generated_plan call must never see section 12's real content — this
    is what makes independence a guarantee rather than an instruction (prompt
    wording alone proved insufficient; see GAPS.md)."""
    text = (
        "11. Corrective Action & Preventive Action: BMR shall be revised. Due Date: 12/08/2025\n"
        "12. CAPA EFFECTIVENESS CHECK PLAN: IP & FP assay data shall be monitored for 90 days "
        "or 10 batches whichever is earlier. Effectiveness Criteria: CpK improvement. QA.\n"
        "13. List of Annexures: Annexure 1 - Investigation plan\n"
    )
    redacted = strip_section_12(text)

    assert "90 days" not in redacted
    assert "CpK improvement" not in redacted
    assert "BMR shall be revised" in redacted  # section 11 preserved
    assert "List of Annexures" in redacted  # section 13 preserved


def test_strip_section_12_skips_table_of_contents_reference():
    """The heading also appears in a table of contents earlier in the report —
    only the LAST occurrence (the real section) should be redacted."""
    text = (
        "Table of Contents: ... 12 Effectiveness check plan 24 ...\n"
        "11. Corrective Action: BMR revision.\n"
        "12. EFFECTIVENESS CHECK PLAN: Real criteria, 10 batches, QA.\n"
        "13. List of Attachments: Annexure 1\n"
    )
    redacted = strip_section_12(text)

    assert "Real criteria" not in redacted
    assert "Table of Contents" in redacted
    assert "BMR revision" in redacted


def test_strip_section_12_no_heading_returns_text_unchanged():
    text = "This report has no effectiveness-check-plan-style heading at all."
    assert strip_section_12(text) == text


def test_kpi_and_acceptance_criteria_both_empty_is_allowed():
    """A genuinely blank EC plan (report's own table is all 'NA') means both
    fields are legitimately '' — that must NOT be rejected as duplication."""
    EffectivenessCheckExtraction(
        reasoning=ExtractionReasoning(
            effectiveness_plan_quote="not present",
            monitoring_method_timing_evidence="No effectiveness plan is stated.",
            monitoring_method_timing="not stated",
        ),
        kpi="",
        monitoring_method="Not clearly classifiable",
        time_horizon="",
        acceptance_criteria="",
        responsible_party="",
        capa_due_date="",
    )


def test_kpi_and_acceptance_criteria_both_non_empty_and_equal_is_rejected():
    with pytest.raises(ValidationError):
        EffectivenessCheckExtraction(
            reasoning=ExtractionReasoning(
                effectiveness_plan_quote="x",
                monitoring_method_timing_evidence="y",
                monitoring_method_timing="prospective",
            ),
            kpi="same text",
            monitoring_method="Monitoring",
            time_horizon="",
            acceptance_criteria="same text",
            responsible_party="QA",
            capa_due_date="",
        )


def _extraction(**overrides) -> EffectivenessCheckExtraction:
    defaults = dict(
        reasoning=ExtractionReasoning(
            effectiveness_plan_quote="IP & FP assay data shall be monitored for 90 days post-implementation.",
            monitoring_method_timing_evidence="Data comes from batches produced after the CAPA.",
            monitoring_method_timing="prospective",
        ),
        kpi="",
        monitoring_method="Not clearly classifiable",
        time_horizon="",
        acceptance_criteria="",
        responsible_party="",
        capa_due_date="",
    )
    defaults.update(overrides)
    return EffectivenessCheckExtraction(**defaults)


def _generated_plan(**overrides) -> GeneratedEffectivenessPlan:
    defaults = dict(
        applicability_reason=(
            "Section 11 proposes a real CAPA action (SCADA space indicator and alarm), "
            "so a plan is applicable."
        ),
        applicable="yes — a CAPA action is proposed in this report",
        grounding=EffectivenessPlanGrounding(
            root_cause_basis="Database space limit reached due to unwanted diagnostic files.",
            preceding_evidence_quote="not available",
            sop_category="Improvement in Key performance indicators (KPIs)",
        ),
        capa_description="Addition of a database-space indicator and alarm at 95% full.",
        effectiveness_check="Monitor SCADA database space utilization following implementation.",
        effectiveness_criteria="Alarm should trigger correctly at 95% capacity with no missed alerts.",
        responsibility="QA",
        duration_rationale=(
            "No Risk Assessment/RPN section was found to calibrate against. The fix is an "
            "engineered/system change (SCADA indicator and alarm), so an extended window is used."
        ),
        duration_tier=(
            "extended (8-10 batches, ~60-90 days) — low risk, a procedural/training-based fix, "
            "or no risk data to calibrate against"
        ),
        monitoring_duration="10 batches or 90 days, whichever is earlier",
    )
    defaults.update(overrides)
    return GeneratedEffectivenessPlan(**defaults)


def test_generated_plan_not_applicable_with_all_fields_empty_is_allowed():
    """No CAPA exists in the report — every field correctly left empty."""
    GeneratedEffectivenessPlan(
        applicability_reason=(
            "Section 11 contains no CAPA action — the report explicitly states no "
            "assignable root cause was found and no CAPA is warranted."
        ),
        applicable="no — the report explicitly states no CAPA is warranted or proposed",
        grounding=EffectivenessPlanGrounding(
            root_cause_basis="", preceding_evidence_quote="", sop_category="Other"
        ),
        capa_description="",
        effectiveness_check="",
        effectiveness_criteria="",
        responsibility="",
        duration_rationale="",
        duration_tier="not applicable — no CAPA action exists in this report to monitor",
        monitoring_duration="",
    )


def test_generated_plan_not_applicable_with_populated_field_is_rejected():
    """The bug this validator fixes: a report with no CAPA at all (e.g.
    RCI - Cholecalciferol.pdf) must not get a fabricated duration just because
    generated_plan drafted a full plan anyway."""
    with pytest.raises(ValidationError):
        GeneratedEffectivenessPlan(
            applicability_reason="No CAPA is warranted.",
            applicable="no — the report explicitly states no CAPA is warranted or proposed",
            grounding=EffectivenessPlanGrounding(
                root_cause_basis="", preceding_evidence_quote="", sop_category="Other"
            ),
            capa_description="",
            effectiveness_check="",
            effectiveness_criteria="",
            responsibility="",
            duration_rationale="",
            duration_tier="not applicable — no CAPA action exists in this report to monitor",
            monitoring_duration="10 batches or 90 days, whichever is earlier",
        )


def test_generated_plan_not_applicable_with_wrong_tier_is_rejected():
    with pytest.raises(ValidationError):
        GeneratedEffectivenessPlan(
            applicability_reason="No CAPA is warranted.",
            applicable="no — the report explicitly states no CAPA is warranted or proposed",
            grounding=EffectivenessPlanGrounding(
                root_cause_basis="", preceding_evidence_quote="", sop_category="Other"
            ),
            capa_description="",
            effectiveness_check="",
            effectiveness_criteria="",
            responsibility="",
            duration_rationale="",
            duration_tier=(
                "extended (8-10 batches, ~60-90 days) — low risk, a procedural/"
                "training-based fix, or no risk data to calibrate against"
            ),
            monitoring_duration="",
        )


def test_generated_plan_applicable_yes_is_unaffected_by_not_applicable_validator():
    """A normal, fully-populated plan (applicable == yes) must not be disturbed
    by the not-applicable validator."""
    plan = _generated_plan()
    assert plan.capa_description
    assert plan.monitoring_duration


def _rule_critiques(critiques, rule4_classification="(e) none found") -> EffectivenessCheckRuleCritiques:
    return EffectivenessCheckRuleCritiques(
        reasoning=CritiqueReasoning(
            rule4_candidate_quote="none found",
            rule4_classification=rule4_classification,
        ),
        rule_critiques=[
            RuleCritique(rule_number=1, rule_name="SMART CAPA Plan", critique=critiques[0]),
            RuleCritique(
                rule_number=2,
                rule_name="Effectiveness Plan Identified or Rationale Given",
                critique=critiques[1],
            ),
            RuleCritique(rule_number=3, rule_name="Sufficient Data Points", critique=critiques[2]),
            RuleCritique(
                rule_number=4,
                rule_name="No Adverse Impact / Risk Minimization",
                critique=critiques[3] if rule4_classification != "(d) genuine implementation-risk statement" else "",
            ),
        ],
        overall_assessment="test",
    )


def test_rule1_flagged_and_due_date_blank_is_allowed():
    """capa_due_date is blank AND Rule 1 already flags it — consistent, no gap-filling needed."""
    EffectivenessCheckExtractionAndCritique(
        extraction=_extraction(capa_due_date=""),
        rule_critiques=_rule_critiques(
            ["No due date is stated for the CAPA action.", "", "", "No risk statement."]
        ),
    )


def test_rule1_empty_and_due_date_present_is_allowed():
    """A real capa_due_date means Time-bound is satisfied — Rule 1 correctly stays empty."""
    EffectivenessCheckExtractionAndCritique(
        extraction=_extraction(capa_due_date="12/08/2025"),
        rule_critiques=_rule_critiques(["", "", "", "No risk statement."]),
    )


def test_rule1_empty_and_due_date_blank_is_rejected():
    """The bug this validator fixes: a blank due date with no due-date column at all
    must not silently pass Rule 1 — this was observed live on RCI - Griseofulvin.pdf,
    where the CAPA table's Due Date read 'Not applicable' and Rule 1 never fired."""
    with pytest.raises(ValidationError):
        EffectivenessCheckExtractionAndCritique(
            extraction=_extraction(capa_due_date=""),
            rule_critiques=_rule_critiques(["", "", "", "No risk statement."]),
        )


def test_rule3_cleared_when_rule2_fails():
    """Rule 2 failing means no plan exists at all — Rule 3 has nothing to judge and
    must be silently cleared rather than double-counting the same gap."""
    result = EffectivenessCheckExtractionAndCritique(
        extraction=_extraction(capa_due_date="12/08/2025"),
        rule_critiques=_rule_critiques(
            [
                "",
                "No plan or rationale is stated.",
                "No data points are stated.",
                "No risk statement.",
            ]
        ),
    )
    assert result.rule_critiques.rule_critiques[2].critique == ""


def test_rule3_preserved_when_rule2_passes():
    """A real plan present but genuinely lacking sufficient data points is a true
    Rule 3 gap and must not be cleared just because Rule 2 passed."""
    result = EffectivenessCheckExtractionAndCritique(
        extraction=_extraction(capa_due_date="12/08/2025"),
        rule_critiques=_rule_critiques(
            ["", "", "No monitoring duration or batch count is stated.", "No risk statement."]
        ),
    )
    assert result.rule_critiques.rule_critiques[2].critique == "No monitoring duration or batch count is stated."


def _extraction_with_quote(quote: str, **overrides) -> EffectivenessCheckExtraction:
    return _extraction(
        reasoning=ExtractionReasoning(
            effectiveness_plan_quote=quote,
            monitoring_method_timing_evidence="No monitoring data is stated.",
            monitoring_method_timing="not stated",
        ),
        **overrides,
    )


def test_rule2_bare_placeholder_and_flagged_is_allowed():
    """A bare 'NA' quote AND Rule 2 already flags it — consistent, no gap-filling needed."""
    EffectivenessCheckExtractionAndCritique(
        extraction=_extraction_with_quote("NA NA NA NA NA", capa_due_date=""),
        rule_critiques=_rule_critiques(
            [
                "No due date is stated.",
                "No plan or rationale for its absence is stated.",
                "",
                "No risk statement.",
            ]
        ),
    )


def test_rule2_bare_placeholder_and_empty_is_rejected():
    """The bug this validator fixes: a bare 'Not applicable' with no justifying
    clause must not silently pass Rule 2 — observed live on HIGH SCORING 1.docx,
    where the model extracted quote='Not applicable' yet left Rule 2 empty."""
    with pytest.raises(ValidationError):
        EffectivenessCheckExtractionAndCritique(
            extraction=_extraction_with_quote("Not applicable", capa_due_date="30/09/2025"),
            rule_critiques=_rule_critiques(["", "", "", "No risk statement."]),
        )


def test_rule2_real_rationale_and_empty_is_allowed():
    """A genuine justifying clause (not just a bare placeholder) legitimately
    satisfies Rule 2 and must not be forced to fail."""
    EffectivenessCheckExtractionAndCritique(
        extraction=_extraction_with_quote(
            "Since no CAPA has been recommended, effectiveness check shall be "
            "considered as not applicable.",
            capa_due_date="15/01/2026",
        ),
        rule_critiques=_rule_critiques(["", "", "", "No risk statement."]),
    )


def test_analyse_rejects_unsupported_file_type():
    response = client.post(
        "/capa-depth-effectiveness/analyse?event_type=OOS",
        files={"file": ("report.txt", b"not a docx", "text/plain")},
    )

    assert response.status_code == 415
    assert "supported" in response.json()["detail"].lower()


def _fake_depth_actions() -> CAPADepthClassification:
    return CAPADepthClassification(
        product_batch_reference="Batch 7261770A",
        root_cause_summary="Database space limit reached due to unwanted diagnostic files.",
        actions=[
            CAPAActionClassification(
                action_description=(
                    "Addition of an indicator of the Database space consumed vs. available on "
                    "the SCADA main page, plus an alarm at 95% full."
                ),
                hierarchy_rationale=(
                    "An alarm at a threshold matches the SOP's Level 3 example verbatim."
                ),
                hierarchy_level=3,
                hierarchy_level_label="Detection by technology",
            )
        ],
    )


def _fake_extraction_critique_result() -> EffectivenessCheckExtractionAndCritique:
    return EffectivenessCheckExtractionAndCritique(
        extraction=EffectivenessCheckExtraction(
            reasoning=ExtractionReasoning(
                effectiveness_plan_quote=(
                    "The implemented system should indicate the alarm on filling 95% of the data"
                ),
                monitoring_method_timing_evidence=(
                    "The alarm is watched going forward after implementation, not reviewing a "
                    "pre-existing dataset."
                ),
                monitoring_method_timing="prospective",
            ),
            kpi="Alarm fires correctly at 95% database capacity",
            monitoring_method="Monitoring",
            time_horizon="",
            acceptance_criteria="No repeated occurrence with same cause",
            responsible_party="QA",
            capa_due_date="15/03/2026",
        ),
        rule_critiques=EffectivenessCheckRuleCritiques(
            reasoning=CritiqueReasoning(
                rule4_candidate_quote=(
                    "The alarm-based detection was verified not to disrupt existing SCADA "
                    "monitoring functions."
                ),
                rule4_classification="(d) genuine implementation-risk statement",
            ),
            rule_critiques=[
                RuleCritique(rule_number=1, rule_name="SMART CAPA Plan", critique=""),
                RuleCritique(
                    rule_number=2,
                    rule_name="Effectiveness Plan Identified or Rationale Given",
                    critique="",
                ),
                RuleCritique(
                    rule_number=3,
                    rule_name="Sufficient Data Points",
                    critique="No monitoring duration or batch count is stated.",
                ),
                RuleCritique(
                    rule_number=4,
                    rule_name="No Adverse Impact / Risk Minimization",
                    critique="",
                ),
            ],
            overall_assessment="Effectiveness plan is present but lacks a defined monitoring period.",
        ),
    )


def test_analyse_returns_valid_shape_for_docx(monkeypatch):
    async def fake_save_upload(file, suffix):
        return Path("/tmp/fake.docx")

    async def fake_extract_docx_text(temp_path):
        return "Full RCI report text..."

    def fake_cleanup(temp_path):
        return None

    async def fake_get_structured_response(self, user_prompt, structure, system_prompt=None):
        if structure is CAPADepthClassification:
            return _fake_depth_actions()
        if structure is EffectivenessCheckExtractionAndCritique:
            return _fake_extraction_critique_result()
        return _generated_plan()

    monkeypatch.setattr(f"{ROUTE_MODULE}.save_upload", fake_save_upload)
    monkeypatch.setattr(f"{ROUTE_MODULE}.extract_docx_text", fake_extract_docx_text)
    monkeypatch.setattr(f"{ROUTE_MODULE}.cleanup", fake_cleanup)
    monkeypatch.setattr(
        "src.llm.client.LLMClient.get_structured_response", fake_get_structured_response
    )

    response = client.post(
        "/capa-depth-effectiveness/analyse?event_type=Deviation",
        files={
            "file": (
                "450141_RCI Report.docx",
                b"fake docx bytes",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["event_type"] == "Deviation"
    assert len(body["capa_depth"]["actions"]) == 1 and body["capa_depth"]["actions"][0]["hierarchy_level"] == 3
    assert len(body["effectiveness_check"]["rule_critiques"]["rule_critiques"]) == 4
    assert body["effectiveness_check"]["extraction"]["monitoring_method"] == "Monitoring"


@pytest.mark.asyncio
async def test_call_with_retry_succeeds_after_validation_failures():
    attempts = []

    async def flaky_call():
        attempts.append(1)
        if len(attempts) < 3:
            EffectivenessCheckExtraction(
                reasoning=ExtractionReasoning(
                    effectiveness_plan_quote="x",
                    monitoring_method_timing_evidence="y",
                    monitoring_method_timing="prospective",
                ),
                kpi="same text",
                monitoring_method="Monitoring",
                time_horizon="",
                acceptance_criteria="same text",  # triggers _kpi_not_duplicated
                responsible_party="QA",
                capa_due_date="15/03/2026",
            )
        return "ok"

    result = await call_with_retry(flaky_call, max_attempts=3, label="test")

    assert result == "ok"
    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_call_with_retry_gives_up_after_max_attempts():
    async def always_fails():
        EffectivenessCheckExtraction(
            reasoning=ExtractionReasoning(
                effectiveness_plan_quote="x",
                monitoring_method_timing_evidence="y",
                monitoring_method_timing="prospective",
            ),
            kpi="same text",
            monitoring_method="Monitoring",
            time_horizon="",
            acceptance_criteria="same text",
            responsible_party="QA",
            capa_due_date="15/03/2026",
        )
        return "never reached"

    with pytest.raises(ValidationError):
        await call_with_retry(always_fails, max_attempts=2, label="test")


def test_analyse_returns_valid_shape_for_pdf(monkeypatch):
    async def fake_save_upload(file, suffix):
        return Path("/tmp/fake.pdf")

    def fake_cleanup(temp_path):
        return None

    async def fake_upload_file(self, file_path):
        return "file-abc123"

    async def fake_delete_file(self, file_id):
        return None

    async def fake_extract_pdf_text(temp_path):
        return "Full RCI report text..."

    async def fake_get_structured_response_from_file(
        self, file_id, *, user_prompt, structure, system_prompt=None
    ):
        assert file_id == "file-abc123"
        if structure is CAPADepthClassification:
            return _fake_depth_actions()
        return _fake_extraction_critique_result()

    async def fake_get_structured_response(self, user_prompt, structure, system_prompt=None):
        return _generated_plan()

    monkeypatch.setattr(f"{ROUTE_MODULE}.save_upload", fake_save_upload)
    monkeypatch.setattr(f"{ROUTE_MODULE}.cleanup", fake_cleanup)
    monkeypatch.setattr(f"{ROUTE_MODULE}.extract_pdf_text", fake_extract_pdf_text)
    monkeypatch.setattr("src.llm.client.LLMClient.upload_file", fake_upload_file)
    monkeypatch.setattr("src.llm.client.LLMClient.delete_file", fake_delete_file)
    monkeypatch.setattr(
        "src.llm.client.LLMClient.get_structured_response_from_file",
        fake_get_structured_response_from_file,
    )
    monkeypatch.setattr(
        "src.llm.client.LLMClient.get_structured_response", fake_get_structured_response
    )

    response = client.post(
        "/capa-depth-effectiveness/analyse?event_type=Deviation",
        files={"file": ("450141_RCI Report.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["event_type"] == "Deviation"
    assert len(body["capa_depth"]["actions"]) == 1 and body["capa_depth"]["actions"][0]["hierarchy_level"] == 3
    assert len(body["effectiveness_check"]["rule_critiques"]["rule_critiques"]) == 4
