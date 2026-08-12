import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, status

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
from src.config.settings import settings
from src.llm.client import LLMClient
from src.utils.deps import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rci-report", tags=["RCI Report"])


def _load_prompt(filename: str) -> str:
    return (settings.PROMPTS_DIR / "rci_report" / filename).read_text(encoding="utf-8")


guard_rail_text = (settings.PROMPTS_DIR / "guardrail.txt").read_text(encoding="utf-8")

description_of_event_system_prompt = _load_prompt("description_of_event_system.txt") + "\n" + guard_rail_text
initial_impact_assessment_system_prompt = _load_prompt("initial_impact_assessment_system.txt") + "\n" + guard_rail_text
history_review_narrative_system_prompt = _load_prompt("history_review_narrative_system.txt") + "\n" + guard_rail_text
investigation_task_system_prompt = _load_prompt("investigation_task_system.txt") + "\n" + guard_rail_text
root_cause_conclusion_system_prompt = _load_prompt("root_cause_conclusion_system.txt") + "\n" + guard_rail_text
impact_batch_disposition_system_prompt = _load_prompt("impact_batch_disposition_system.txt") + "\n" + guard_rail_text
correction_remedial_action_system_prompt = _load_prompt("correction_remedial_action_system.txt") + "\n" + guard_rail_text
capa_system_prompt = _load_prompt("capa_system.txt") + "\n" + guard_rail_text
risk_factors_system_prompt = _load_prompt("risk_factors_system.txt") + "\n" + guard_rail_text
executive_summary_system_prompt = _load_prompt("executive_summary_system.txt") + "\n" + guard_rail_text
capa_effectiveness_check_plan_system_prompt = (
    _load_prompt("capa_effectiveness_check_plan_system.txt") + "\n" + guard_rail_text
)


def _tw_summary(ctx: RciReportContext) -> str:
    """Flatten non-empty trackwise fields into 'key: value' lines for prompt input."""
    return "\n".join(
        f"- {k}: {v}" for k, v in ctx.trackwise_fields.items() if v not in (None, "", [])
    ) or "(no non-empty trackwise fields)"


# ── Wave 1: 9 independent tasks — each grounded only in ctx ──────────────


async def _generate_description_of_event(llm: LLMClient, ctx: RciReportContext) -> DescriptionOfEventSection:
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\nTrackWise Fields:\n{_tw_summary(ctx)}\n\n"
        f"Manual Entries (investigator-supplied, use where TrackWise has no field):\n"
        f"{json.dumps(ctx.manual_entries)}"
    )
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=description_of_event_system_prompt,
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
            system_prompt=initial_impact_assessment_system_prompt,
            user_prompt=user_prompt,
            structure=InitialImpactAssessmentSection,
        ),
        label="initial_impact_assessment",
    )


async def _generate_investigation_task(llm: LLMClient, ctx: RciReportContext) -> InvestigationTaskSection:
    rci_plan_text = json.dumps([section.model_dump() for section in ctx.rci_plan_sections])
    task_critique_text = json.dumps([item.model_dump() for item in ctx.task_critique])
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\nRCI Plan Sections:\n{rci_plan_text}\n\n"
        f"Task Critique Output:\n{task_critique_text}"
    )
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=investigation_task_system_prompt,
            user_prompt=user_prompt,
            structure=InvestigationTaskSection,
        ),
        label="investigation_task",
    )


async def _generate_root_cause_conclusion(llm: LLMClient, ctx: RciReportContext) -> RootCauseConclusionSection:
    rc = ctx.accepted_rc_conclusion
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\n"
        f"Accepted Root Cause Conclusion:\n{rc.rc_conclusion_text}\n\n"
        # These DB-sourced hints predate the 2026-08-09 taxonomy correction and use
        # a different 3-tier scheme (broad_category/category/root_cause_sub_category)
        # than the 6M-factor-based output this section now produces — real reports
        # for the same records these hints came from don't render this 3-tier
        # scheme either, so treat them as loose supplementary signal only, not a
        # literal mapping onto the output taxonomy below. See GAPS.md.
        f"Loose taxonomy hints from upstream critique (may be blank, may not align "
        f"with the 6M-factor taxonomy below): broad_category={rc.broad_category}, "
        f"category={rc.category}, root_cause_sub_category={rc.root_cause_sub_category}\n\n"
        f"Known repeat-occurrence flag (may be null): {rc.is_repeat_occurrence}\n\n"
        f"Supplementary raw TrackWise root-cause text (may overlap or be blank):\n"
        f"{ctx.root_cause_conclusion_text_clean}"
    )
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=root_cause_conclusion_system_prompt,
            user_prompt=user_prompt,
            structure=RootCauseConclusionSection,
        ),
        label="root_cause_conclusion",
    )


async def _generate_impact_assessment(
    llm: LLMClient, ctx: RciReportContext
) -> ImpactAssessmentBatchDispositionSection:
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\n"
        f"Accepted Root Cause Conclusion:\n{ctx.accepted_rc_conclusion.rc_conclusion_text}\n\n"
        f"Cleaned Impact Details:\n{ctx.impact_details_text_clean}\n\n"
        f"Medical/impact-related TrackWise fields (Market Complaint only, may be blank):\n"
        f"medical_investigation_summary={ctx.tw('medical_investigation_summary')}, "
        f"medical_impact_analysis={ctx.tw('medical_impact_analysis')}, "
        f"health_hazard_evaluation={ctx.tw('health_hazard_evaluation')}\n\n"
        f"Impact justification (OOS/OOT only, may be blank): {ctx.tw('impact_justification')}\n\n"
        f"Impact on other batches (OOS/OOT and Market Complaint, may be blank): "
        f"{ctx.tw('impact_on_other_batches')}"
    )
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=impact_batch_disposition_system_prompt,
            user_prompt=user_prompt,
            structure=ImpactAssessmentBatchDispositionSection,
        ),
        label="impact_assessment_batch_disposition",
    )


async def _generate_correction_remedial(
    llm: LLMClient, ctx: RciReportContext
) -> CorrectionRemedialActionSection:
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\n"
        f"Cleaned Correction/Remedial Action text:\n{ctx.correction_remedial_text_clean}"
    )
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=correction_remedial_action_system_prompt,
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
            system_prompt=capa_system_prompt, user_prompt=user_prompt, structure=CAPASection,
        ),
        label="capa",
    )


async def _generate_capa_effectiveness_check_plan_item(
    llm: LLMClient, ctx: RciReportContext, capa_item
) -> CAPAEffectivenessPlanItem:
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=capa_effectiveness_check_plan_system_prompt,
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
            system_prompt=risk_factors_system_prompt, user_prompt=user_prompt, structure=GeneratedRiskFactors,
        ),
        label="risk_factors",
    )
    return build_risk_assessment_section(generated)


async def _generate_executive_summary(
    llm: LLMClient,
    ctx: RciReportContext,
    description_of_event: DescriptionOfEventSection,
    initial_impact_assessment: InitialImpactAssessmentSection,
    investigation_task: InvestigationTaskSection,
    root_cause: RootCauseConclusionSection,
    impact_assessment: ImpactAssessmentBatchDispositionSection,
    correction_remedial: CorrectionRemedialActionSection,
    capa: CAPASection,
) -> ExecutiveSummarySection:
    user_prompt = (
        f"Event Type: {ctx.event_type}\n\n"
        f"Description of Event:\n{description_of_event.model_dump_json()}\n\n"
        f"Initial Impact Assessment:\n{initial_impact_assessment.model_dump_json()}\n\n"
        f"Investigation Task:\n{investigation_task.model_dump_json()}\n\n"
        f"Root Cause Conclusion:\n{root_cause.model_dump_json()}\n\n"
        f"Impact Assessment & Batch Disposition:\n{impact_assessment.model_dump_json()}\n\n"
        f"Correction & Remedial Action:\n{correction_remedial.model_dump_json()}\n\n"
        f"CAPA:\n{capa.model_dump_json()}"
    )
    return await call_with_retry(
        lambda: llm.get_structured_response(
            system_prompt=executive_summary_system_prompt,
            user_prompt=user_prompt,
            structure=ExecutiveSummarySection,
        ),
        label="executive_summary",
    )


@router.post(
    "/generate",
    response_model=RciReportResponse,
    summary="Generate a full RCI Report from TrackWise fields and already-critiqued upstream artifacts",
)
async def generate_rci_report(request: RciReportGenerationRequest) -> RciReportResponse:
    ctx = build_report_context(request)
    llm = LLMClient()
    pool = await get_db_pool()

    try:
        (
            description_of_event,
            initial_impact_assessment,
            history_review,
            investigation_task,
            root_cause,
            impact_assessment,
            correction_remedial,
            capa,
            capa_effectiveness_check_plan,
        ) = await asyncio.gather(
            _generate_description_of_event(llm, ctx),
            _generate_initial_impact_assessment(llm, ctx),
            generate_history_review(
                llm,
                pool,
                event_type=ctx.event_type,
                search_query=ctx.tw("description") or ctx.event_type,
                lookback_months=ctx.history_lookback_months,
                narrative_system_prompt=history_review_narrative_system_prompt,
                exclude_id=ctx.deviation_id,
            ),
            _generate_investigation_task(llm, ctx),
            _generate_root_cause_conclusion(llm, ctx),
            _generate_impact_assessment(llm, ctx),
            _generate_correction_remedial(llm, ctx),
            _generate_capa(llm, ctx),
            _generate_capa_effectiveness_check_plan(llm, ctx),
        )

        # No confirmed structured data source yet for a genuine "batches
        # manufactured in the lookback window" count (all templates require it,
        # both real reports checked render it) — see GAPS.md. Sourced from
        # manual_entries only until one is found.
        batches_manufactured_note = ctx.manual_entries.get("batches_manufactured_in_lookback")
        if batches_manufactured_note:
            history_review = history_review.model_copy(
                update={"batches_manufactured_note": batches_manufactured_note}
            )

        risk_assessment, executive_summary = await asyncio.gather(
            _generate_risk_assessment(llm, ctx, root_cause, impact_assessment, history_review),
            _generate_executive_summary(
                llm,
                ctx,
                description_of_event,
                initial_impact_assessment,
                investigation_task,
                root_cause,
                impact_assessment,
                correction_remedial,
                capa,
            ),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("RCI report generation failed for event_type=%s", request.event_type)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate RCI report",
        )

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
    )
