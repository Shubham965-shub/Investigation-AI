import asyncio
import json
import logging
from typing import Any, Awaitable, Dict, List, Optional, Tuple

from fastapi import APIRouter

from src.agents.capa_depth_effectiveness.api.services.capa_depth_effectiveness_service import (
    call_with_retry,
)
from src.agents.rci_report.api.schemas.define import (
    DescriptionOfEventSection,
    ExecutiveSummarySection,
    InitialImpactAssessmentSection,
)
from src.agents.rci_report.api.schemas.improve_control import (
    CAPAEffectivenessCheckPlanSection,
    CAPAEffectivenessPlanItem,
    CAPASection,
    CorrectionRemedialActionSection,
)
from src.agents.rci_report.api.schemas.measure_analyze import (
    GeneratedRiskFactors,
    HistoryReviewSection,
    ImpactAssessmentBatchDispositionSection,
    InvestigationTaskSection,
    RiskAssessmentSection,
    RootCauseConclusionSection,
)
from src.agents.rci_report.api.schemas.request import RciReportGenerationRequest
from src.agents.rci_report.api.schemas.response import AnnexuresSection, ApprovalSection, RciReportResponse
from src.agents.rci_report.api.services.context import RciReportContext, build_report_context
from src.agents.rci_report.api.services.history_review_service import generate_history_review
from src.agents.rci_report.api.services.risk_scoring import build_risk_assessment_section
from src.llm.client import LLMClient
from src.utils.deps import get_db_pool, get_prompt_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rci-report", tags=["RCI Report"])


def _rci_report_prompt(name: str) -> str:
    """A rci_report/<name> system prompt with the shared guardrail appended
    — every one of this file's system prompts follows this same
    concatenation, previously built eagerly at import time from static
    .txt files; now resolved from PromptRegistry at call time instead
    (2026-09-02)."""
    registry = get_prompt_registry()
    return registry.get(f"rci_report/{name}") + "\n" + registry.get("guardrail")


def _tw_summary(ctx: RciReportContext) -> str:
    """Flatten non-empty trackwise fields into 'key: value' lines for prompt input."""
    return "\n".join(
        f"- {k}: {v}" for k, v in ctx.trackwise_fields.items() if v not in (None, "", [])
    ) or "(no non-empty trackwise fields)"


# errors[] is keyed by these same field names (matching RciReportResponse) so
# callers can match programmatically — this is purely for making the message
# *text* self-describing, both for a section's own error and for naming a
# failed/skipped section inside another section's dependency message.
_SECTION_DISPLAY_NAMES: Dict[str, str] = {
    "description_of_event": "Description of Event",
    "initial_impact_assessment": "Initial Impact Assessment",
    "history_review": "History Review",
    "investigation_task": "Investigation Task",
    "root_cause_conclusion": "Root Cause Conclusion",
    "impact_assessment_batch_disposition": "Impact Assessment & Batch Disposition",
    "risk_assessment": "Risk Assessment",
    "correction_remedial_action": "Correction & Remedial Action",
    "capa": "CAPA",
    "capa_effectiveness_check_plan": "CAPA Effectiveness Check Plan",
    "executive_summary": "Executive Summary",
}


def _display_name(section_key: str) -> str:
    return _SECTION_DISPLAY_NAMES.get(section_key, section_key)


# Union of every "required" attribute name across the Deviation/OOS/OOT/Market
# Complaint trackwise schemas (see shared/schemas.py) — safe to over-list here
# since ctx.missing_required_tw_fields is already scoped to only the fields
# required by *this* record's actual event type; irrelevant names here just
# never appear in that set. Description of Event and Initial Impact Assessment
# are the only two sections built purely from the raw TW field dump
# (_tw_summary) rather than an already-critiqued upstream artifact (RC & CAPA
# Critique output, rci_plan_sections, task_critique) — every other section is
# grounded in one of those instead, so a missing base TW field doesn't block
# them the way it blocks these two.
_DESCRIPTIVE_TW_FIELDS = {
    # Deviation
    "title", "batch_number_ar_number", "product_material_code", "product_material_name",
    "deviation_to", "equipment_name", "description", "instrument_id_number",
    "name_of_the_instrument", "observed_by", "deviation_number", "date_opened",
    "observation_date", "observation_time", "failure_duration", "related_market",
    "related_customer", "equipment_id", "equipment_number", "deviation_owner",
    "originator", "impact_on_deviation_batches", "immediate_cause_known", "cause_detail",
    # OOS/OOT
    "laboratory_details", "specification_number", "stability_condition",
    "stability_protocol_number", "labelled_storage_conditions", "product_type",
    "stp_number", "stability_time_point",
    # Market Complaint
    "date_complaint_received", "complaint_reported_by", "reference_complaint_number",
    "products_information", "dosage_form", "market", "product_manufacturing_info",
}
_SECTION_REQUIRED_TW_FIELDS: Dict[str, set] = {
    "description_of_event": _DESCRIPTIVE_TW_FIELDS,
    "initial_impact_assessment": _DESCRIPTIVE_TW_FIELDS,
}


def _blank(value: Any) -> bool:
    return not str(value or "").strip()


def _section_missing_deps(ctx: RciReportContext, section_key: str) -> List[str]:
    """Human-readable descriptions of the specific TrackWise/API field(s) this
    section is missing — always used to name what's missing in errors[]; for
    section_keys with no entry in _SECTION_REQUIRED_TW_FIELDS this list is
    also fully determinative of whether to skip (see _section_should_skip).
    """
    missing: List[str] = []

    required_tw = _SECTION_REQUIRED_TW_FIELDS.get(section_key)
    if required_tw:
        missing += [
            f"TrackWise field '{name}'" for name in sorted(ctx.missing_required_tw_fields & required_tw)
        ]

    # Correction/Remedial Action and Impact Assessment & Batch Disposition are
    # intentionally NOT grounded on any TrackWise field (2026-08-26 for the
    # former, 2026-09-01 for the latter, both per the user) — TrackWise's
    # free-text fields here are often just audit-log stubs, not the real
    # investigator-drafted content, so both sections are sourced solely from
    # the uploaded RC & CAPA document's own text.
    if section_key == "correction_remedial_action" and _blank(ctx.uploaded_correction_remedial_text):
        missing.append("no uploaded RC & CAPA document text")

    if section_key == "impact_assessment_batch_disposition" and _blank(ctx.uploaded_impact_assessment_text):
        missing.append("no uploaded RC & CAPA document text")

    if section_key in ("root_cause_conclusion", "impact_assessment_batch_disposition"):
        if _blank(ctx.accepted_rc_conclusion.rc_conclusion_text):
            missing.append("API field 'accepted_rc_conclusion.rc_conclusion_text'")

    # CAPA is a compile-what-was-already-decided task (see capa_system.txt),
    # not a generative one — it has nothing to compile when the accepted CAPA
    # proposal is genuinely empty (RC & CAPA Critique hasn't produced CAPA
    # items or even a not-applicable justification yet). capa_overall_text is
    # deliberately EXCLUDED from this check (2026-08-25): capa_system.txt
    # gives the model no instruction for what to do with it (it's passed as
    # supplementary context only, never referenced by name in the prompt), so
    # a populated capa_overall_text is not evidence a real CAPA action or a
    # not-applicable decision exists — e.g. it may just be the CAPA Critique
    # step's own gap-commentary summary, present even when capa_items is
    # empty. Gating on it caused generation to be attempted with nothing to
    # compile, which correctly produced empty capa_actions with no
    # justification and crashed CAPASection's own validation instead of
    # skipping cleanly (confirmed live against record 505542).
    if section_key == "capa":
        accepted = ctx.accepted_capa
        if not accepted.capa_items and _blank(accepted.capa_not_applicable_justification):
            missing.append("API field 'accepted_capa' (no CAPA items or not-applicable justification)")

    return missing


def _section_should_skip(ctx: RciReportContext, section_key: str, missing: List[str]) -> bool:
    """Description of Event and Initial Impact Assessment are each built from
    a broad set of ~30 TrackWise fields (_DESCRIPTIVE_TW_FIELDS) via
    _tw_summary, which already omits blank fields from the prompt on its own
    — so one blank required field (e.g. Market Complaint's
    complaint_reported_by) shouldn't block the other ~20+ populated fields
    from ever reaching the LLM. Only skip these two when EVERY relevant
    required field is blank, i.e. there's truly nothing to ground the section
    in.

    Correction & Remedial Action, Root Cause Conclusion, Impact Assessment &
    Batch Disposition, and CAPA are each built from sole-source input(s) —
    the uploaded RC & CAPA document's own text for Correction & Remedial
    Action, that same document's Impact Assessment text plus the
    already-accepted RC conclusion for Impact Assessment & Batch
    Disposition, and an already-accepted API artifact for Root Cause
    Conclusion and CAPA — with no partial middle ground and no workflow/data
    distinction to draw — any missing value there stays fatal.
    """
    if not missing:
        return False

    required_tw = _SECTION_REQUIRED_TW_FIELDS.get(section_key)
    if required_tw is not None:
        relevant_required = ctx.required_tw_fields & required_tw
        relevant_missing = ctx.missing_required_tw_fields & required_tw
        return bool(relevant_required) and relevant_missing == relevant_required

    return True


# ── Wave 1: 9 independent tasks — each grounded only in ctx ──────────────


async def _generate_description_of_event(llm: LLMClient, ctx: RciReportContext) -> DescriptionOfEventSection:
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\nTrackWise Fields:\n{_tw_summary(ctx)}\n\n"
        f"Manual Entries (investigator-supplied, use where TrackWise has no field):\n"
        f"{json.dumps(ctx.manual_entries)}"
    )
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=_rci_report_prompt("description_of_event_system"),
            user_prompt=user_prompt,
            structure=DescriptionOfEventSection,
        ),
        label="description_of_event",
    )


async def _generate_initial_impact_assessment(
    llm: LLMClient, ctx: RciReportContext
) -> InitialImpactAssessmentSection:
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\nTrackWise Fields:\n{_tw_summary(ctx)}\n\n"
        f"Manual Entries:\n{json.dumps(ctx.manual_entries)}"
    )
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=_rci_report_prompt("initial_impact_assessment_system"),
            user_prompt=user_prompt,
            structure=InitialImpactAssessmentSection,
        ),
        label="initial_impact_assessment",
    )


_NO_TASK_EVIDENCE_NOTE = "No Task Critique evidence was available for this task — outcome could not be established."


async def _generate_investigation_task(llm: LLMClient, ctx: RciReportContext) -> InvestigationTaskSection:
    rci_plan_text = json.dumps([section.model_dump() for section in ctx.rci_plan_sections])
    task_critique_text = json.dumps([item.model_dump() for item in ctx.task_critique])
    rc = ctx.accepted_rc_conclusion
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\nRCI Plan Sections:\n{rci_plan_text}\n\n"
        f"Task Critique Output:\n{task_critique_text}\n\n"
        f"Accepted Root Cause Conclusion (identify which task(s) above genuinely "
        f"support this):\n{rc.rc_conclusion_text}\n\n"
        f"Loose taxonomy hints from upstream critique (may be blank, may not align "
        f"with the 6M-factor taxonomy used above): broad_category={rc.broad_category}, "
        f"category={rc.category}, root_cause_sub_category={rc.root_cause_sub_category}"
    )
    result = await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=_rci_report_prompt("investigation_task_system"),
            user_prompt=user_prompt,
            structure=InvestigationTaskSection,
        ),
        label="investigation_task",
    )
    # 2026-09-01, per the user: a task with no Task Critique evidence at all must say so
    # explicitly rather than the LLM writing an outcome with nothing to base it on — the
    # prompt already asks it not to fabricate, but that's not deterministically enforced,
    # so the outcome is overridden here regardless of what the LLM wrote for that tick.
    missing_evidence_ticks = {item.tick for item in ctx.task_critique if not (item.critique or "").strip()}
    if missing_evidence_ticks:
        updated_tasks = [
            task.model_copy(update={"outcome": _NO_TASK_EVIDENCE_NOTE})
            if task.tick in missing_evidence_ticks else task
            for task in result.task_summary.tasks
        ]
        result = result.model_copy(
            update={"task_summary": result.task_summary.model_copy(update={"tasks": updated_tasks})}
        )
    return result


async def _generate_root_cause_conclusion(llm: LLMClient, ctx: RciReportContext) -> RootCauseConclusionSection:
    # No TrackWise field grounds this section (2026-09-01, per the user) — the
    # accepted conclusion (the uploaded RC & CAPA document's own verbatim text,
    # already reviewed and accepted upstream) is the sole source. The old
    # DB-sourced 3-tier taxonomy hints (broad_category/category/
    # root_cause_sub_category) are dropped here too: they predate the
    # 2026-08-09 taxonomy correction and use a scheme real reports never
    # actually render (see GAPS.md) — still passed to Section 5's own prompt,
    # just no longer to this one.
    rc = ctx.accepted_rc_conclusion
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\n"
        f"Accepted Root Cause Conclusion (sole source):\n{rc.rc_conclusion_text}\n\n"
        f"Known repeat-occurrence flag (may be null): {rc.is_repeat_occurrence}"
    )
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=_rci_report_prompt("root_cause_conclusion_system"),
            user_prompt=user_prompt,
            structure=RootCauseConclusionSection,
        ),
        label="root_cause_conclusion",
    )


_IMPACT_CONCLUSION_NOT_STATED = "Not stated in the uploaded RC & CAPA document."


async def _generate_impact_assessment(
    llm: LLMClient, ctx: RciReportContext
) -> ImpactAssessmentBatchDispositionSection:
    # No TrackWise field grounds this section (2026-09-01, per the user) — the
    # uploaded RC & CAPA document's own Impact Assessment text is the sole
    # source for all 12 subsections. The accepted Root Cause Conclusion is
    # passed as cross-reference context only (it's the RC & CAPA report's own
    # already-accepted output, not a TrackWise field).
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\n"
        f"Accepted Root Cause Conclusion (cross-reference context only):\n"
        f"{ctx.accepted_rc_conclusion.rc_conclusion_text}\n\n"
        f"Uploaded RC & CAPA document's own Impact Assessment & Conclusion (Batch disposition) "
        f"text (sole source for all 12 subsections below):\n"
        f"{ctx.uploaded_impact_assessment_text}"
    )
    result = await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=_rci_report_prompt("impact_batch_disposition_system"),
            user_prompt=user_prompt,
            structure=ImpactAssessmentBatchDispositionSection,
        ),
        label="impact_assessment_batch_disposition",
    )
    # 2026-09-01, per the user: the batch-disposition conclusion is "lifted and pasted
    # directly" from the uploaded RC & CAPA document, NEVER LLM-synthesized — mirrors
    # correction_remedial_action's sole-sourcing pattern. Unconditional: the LLM's own
    # attempt at this field (see impact_batch_disposition_system.txt item 12 — told to
    # leave it blank) is always discarded, whether or not a document conclusion was
    # found, so a reader never mistakes an LLM guess for the document's own words.
    result = result.model_copy(
        update={"conclusion": ctx.uploaded_impact_conclusion_text or _IMPACT_CONCLUSION_NOT_STATED}
    )
    return result


async def _generate_correction_remedial(
    llm: LLMClient, ctx: RciReportContext
) -> CorrectionRemedialActionSection:
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\n"
        f"Uploaded RC & CAPA document's own Correction and/or Remedial Action text "
        f"(the sole source for this section — not grounded on TrackWise):\n"
        f"{ctx.uploaded_correction_remedial_text}"
    )
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=_rci_report_prompt("correction_remedial_action_system"),
            user_prompt=user_prompt,
            structure=CorrectionRemedialActionSection,
        ),
        label="correction_remedial_action",
    )


async def _generate_capa(llm: LLMClient, ctx: RciReportContext) -> CAPASection:
    accepted = ctx.accepted_capa
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\n"
        f"Accepted CAPA Proposal:\n{json.dumps(accepted.model_dump())}"
    )
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=_rci_report_prompt("capa_system"), user_prompt=user_prompt, structure=CAPASection,
        ),
        label="capa",
    )


async def _generate_capa_effectiveness_check_plan_item(
    llm: LLMClient, ctx: RciReportContext, capa_item
) -> CAPAEffectivenessPlanItem:
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=_rci_report_prompt("capa_effectiveness_check_plan_system"),
            user_prompt=ctx.effectiveness_plan_evidence_text(capa_item=capa_item),
            structure=CAPAEffectivenessPlanItem,
        ),
        label="capa_effectiveness_plan_item",
    )


async def _generate_capa_effectiveness_check_plan(
    llm: LLMClient, ctx: RciReportContext
) -> CAPAEffectivenessCheckPlanSection:
    """One call PER accepted CAPA item, not one call for all of them combined
    — the real UI renders one effectiveness-check row per CAPA action
    (confirmed 2026-08-06 against the real production UI). Applicability is
    determined deterministically from ctx.accepted_capa (mirroring
    CAPASection's own capa_not_applicable_justification pattern) rather than
    asked of the LLM — whether a CAPA exists is already known structured
    data by this point, not something to infer from document text.
    """
    accepted = ctx.accepted_capa
    if accepted.capa_not_applicable_justification or not accepted.capa_items:
        return CAPAEffectivenessCheckPlanSection(
            capa_not_applicable_justification=(
                accepted.capa_not_applicable_justification
                or "No CAPA items were proposed in the accepted CAPA proposal."
            )
        )
    generated_plans = await asyncio.gather(
        *[
            _generate_capa_effectiveness_check_plan_item(llm, ctx, item)
            for item in accepted.capa_items
        ]
    )
    return CAPAEffectivenessCheckPlanSection(generated_plans=list(generated_plans))


# ── Wave 2: depends on specific Wave-1 results ────────────────────────────


async def _generate_risk_assessment(
    llm: LLMClient,
    ctx: RciReportContext,
    root_cause: RootCauseConclusionSection,
    impact_assessment: ImpactAssessmentBatchDispositionSection,
    history_review: HistoryReviewSection,
) -> RiskAssessmentSection:
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\n"
        f"Root Cause Conclusion:\n{root_cause.model_dump_json()}\n\n"
        f"Impact Assessment & Batch Disposition:\n{impact_assessment.model_dump_json()}\n\n"
        f"History Review:\n{history_review.model_dump_json()}\n\n"
        f"MC confirmation status (None if not applicable/not a Market Complaint): {ctx.mc_confirmed}"
    )
    generated = await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=_rci_report_prompt("risk_factors_system"), user_prompt=user_prompt, structure=GeneratedRiskFactors,
        ),
        label="risk_factors",
    )
    return build_risk_assessment_section(generated)


async def _generate_executive_summary(
    llm: LLMClient,
    ctx: RciReportContext,
    description_of_event: Optional[DescriptionOfEventSection],
    initial_impact_assessment: Optional[InitialImpactAssessmentSection],
    investigation_task: Optional[InvestigationTaskSection],
    root_cause: Optional[RootCauseConclusionSection],
    impact_assessment: Optional[ImpactAssessmentBatchDispositionSection],
    correction_remedial: Optional[CorrectionRemedialActionSection],
    capa: Optional[CAPASection],
) -> ExecutiveSummarySection:
    sections = {
        "Description of Event": description_of_event,
        "Initial Impact Assessment": initial_impact_assessment,
        "Investigation Task": investigation_task,
        "Root Cause Conclusion": root_cause,
        "Impact Assessment & Batch Disposition": impact_assessment,
        "Correction & Remedial Action": correction_remedial,
        "CAPA": capa,
    }
    missing_names = [name for name, value in sections.items() if value is None]

    prompt_parts = [f"Event Type: {ctx.event_type}"]
    prompt_parts += [
        f"{name}:\n{value.model_dump_json()}" for name, value in sections.items() if value is not None
    ]
    if missing_names:
        prompt_parts.append(
            "The following sections were NOT available for this report and must be treated as "
            "not-yet-determined, per the system prompt's rules for missing sections — do not imply "
            "they are complete or fabricate their content: " + ", ".join(missing_names)
        )
    user_prompt = "\n\n".join(prompt_parts)

    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=_rci_report_prompt("executive_summary_system"),
            user_prompt=user_prompt,
            structure=ExecutiveSummarySection,
        ),
        label="executive_summary",
    )


async def _run_named(tasks: Dict[str, Awaitable]) -> Tuple[Dict[str, object], Dict[str, str]]:
    """Runs each named coroutine independently — one section's failure must not
    discard the others' results (mirrors scoring_service.score_report)."""
    keys = list(tasks.keys())
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    values: Dict[str, object] = {}
    errors: Dict[str, str] = {}
    for key, result in zip(keys, results):
        if isinstance(result, BaseException):
            logger.error("RCI report section '%s' failed to generate", key, exc_info=result)
            values[key] = None
            reason = str(result) or result.__class__.__name__
            errors[key] = f"{_display_name(key)}: failed to generate — {reason}"
        else:
            values[key] = result
    return values, errors


@router.post(
    "/generate",
    response_model=RciReportResponse,
    summary="Generate a full RCI Report from TrackWise fields and already-critiqued upstream artifacts",
)
async def generate_rci_report(request: RciReportGenerationRequest) -> RciReportResponse:
    ctx = build_report_context(request)
    llm = LLMClient()
    pool = await get_db_pool()

    errors: Dict[str, str] = {}
    wave1_tasks: Dict[str, Awaitable] = {
        "history_review": generate_history_review(
            llm,
            pool,
            event_type=ctx.event_type,
            search_query=ctx.tw("description") or ctx.event_type,
            lookback_months=ctx.history_lookback_months,
            narrative_system_prompt=_rci_report_prompt("history_review_narrative_system"),
            exclude_id=ctx.deviation_id,
        ),
        "investigation_task": _generate_investigation_task(llm, ctx),
        "capa_effectiveness_check_plan": _generate_capa_effectiveness_check_plan(llm, ctx),
    }
    # Each of these has a specific TW/API field it's substantively built from
    # (see _section_missing_deps) — skip generating a section (rather than
    # running it ungrounded) only when _section_should_skip says there's
    # nothing left to ground it in, and name exactly which field(s) in
    # errors[] instead of a generic failure message. Every other Wave-1
    # section (above) has no single required field this way, so it always
    # runs regardless of what's missing elsewhere.
    for section_key, factory in (
        ("description_of_event", lambda: _generate_description_of_event(llm, ctx)),
        ("initial_impact_assessment", lambda: _generate_initial_impact_assessment(llm, ctx)),
        ("root_cause_conclusion", lambda: _generate_root_cause_conclusion(llm, ctx)),
        ("impact_assessment_batch_disposition", lambda: _generate_impact_assessment(llm, ctx)),
        ("correction_remedial_action", lambda: _generate_correction_remedial(llm, ctx)),
        ("capa", lambda: _generate_capa(llm, ctx)),
    ):
        missing = _section_missing_deps(ctx, section_key)
        if _section_should_skip(ctx, section_key, missing):
            errors[section_key] = (
                f"{_display_name(section_key)}: skipped — required field(s) missing or empty: "
                f"{', '.join(missing)}"
            )
        else:
            wave1_tasks[section_key] = factory()

    wave1, wave1_errors = await _run_named(wave1_tasks)
    errors.update(wave1_errors)

    description_of_event = wave1.get("description_of_event")
    initial_impact_assessment = wave1.get("initial_impact_assessment")
    history_review = wave1.get("history_review")
    investigation_task = wave1.get("investigation_task")
    root_cause = wave1.get("root_cause_conclusion")
    impact_assessment = wave1.get("impact_assessment_batch_disposition")
    correction_remedial = wave1.get("correction_remedial_action")
    capa = wave1.get("capa")
    capa_effectiveness_check_plan = wave1.get("capa_effectiveness_check_plan")

    # No confirmed structured data source yet for a genuine "batches
    # manufactured in the lookback window" count (all templates require it,
    # both real reports checked render it) — see GAPS.md. Sourced from
    # manual_entries only until one is found.
    if history_review is not None:
        batches_manufactured_note = ctx.manual_entries.get("batches_manufactured_in_lookback")
        if batches_manufactured_note:
            history_review = history_review.model_copy(
                update={"batches_manufactured_note": batches_manufactured_note}
            )

    # Wave 2 sections are grounded in specific Wave-1 results — if a section
    # they need failed, running them would crash on None instead of producing
    # a meaningful output, so they're marked failed-by-dependency and skipped.
    wave2_tasks: Dict[str, Awaitable] = {}

    risk_assessment_deps = {
        "root_cause_conclusion": root_cause,
        "impact_assessment_batch_disposition": impact_assessment,
        "history_review": history_review,
    }
    missing = [name for name, value in risk_assessment_deps.items() if value is None]
    if missing:
        errors["risk_assessment"] = (
            f"{_display_name('risk_assessment')}: skipped — dependent section(s) failed to generate: "
            f"{', '.join(_display_name(name) for name in missing)}"
        )
    else:
        wave2_tasks["risk_assessment"] = _generate_risk_assessment(
            llm, ctx, root_cause, impact_assessment, history_review
        )

    executive_summary_deps = {
        "description_of_event": description_of_event,
        "initial_impact_assessment": initial_impact_assessment,
        "investigation_task": investigation_task,
        "root_cause_conclusion": root_cause,
        "impact_assessment_batch_disposition": impact_assessment,
        "correction_remedial_action": correction_remedial,
        "capa": capa,
    }
    missing = [name for name, value in executive_summary_deps.items() if value is None]
    if len(missing) == len(executive_summary_deps):
        errors["executive_summary"] = (
            f"{_display_name('executive_summary')}: skipped — no dependent section(s) generated"
        )
    else:
        wave2_tasks["executive_summary"] = _generate_executive_summary(
            llm,
            ctx,
            description_of_event,
            initial_impact_assessment,
            investigation_task,
            root_cause,
            impact_assessment,
            correction_remedial,
            capa,
        )

    risk_assessment = None
    executive_summary = None
    if wave2_tasks:
        wave2, wave2_errors = await _run_named(wave2_tasks)
        errors.update(wave2_errors)
        risk_assessment = wave2.get("risk_assessment")
        executive_summary = wave2.get("executive_summary")

    return RciReportResponse(
        event_type=request.event_type,
        executive_summary=executive_summary,
        description_of_event=description_of_event,
        initial_impact_assessment=initial_impact_assessment,
        history_review=history_review,
        investigation_task=investigation_task,
        root_cause_conclusion=root_cause,
        impact_assessment_batch_disposition=impact_assessment,
        risk_assessment=risk_assessment,
        correction_remedial_action=correction_remedial,
        capa=capa,
        capa_effectiveness_check_plan=capa_effectiveness_check_plan,
        annexures=request.attachments or AnnexuresSection(),
        approval=request.approval_workflow or ApprovalSection(),
        errors=errors,
    )
