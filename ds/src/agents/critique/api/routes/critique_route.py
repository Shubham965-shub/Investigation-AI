import json
import re
import shutil
import tempfile
import asyncio
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, File, UploadFile, status
from fastapi.responses import JSONResponse

from src.agents.critique.api.schemas import (
    CritiqueInputSchema, CritiqueOutSchema, TaskSchema, CritiqueRCIRequest,
    RCConclusionCritiqueResponse, CAPACritiqueResponse, CAPAItemDetail,
)
from src.agents.critique.api.services.rci_report_extraction import (
    extract_full_document_text, extract_rci_report_sections,
)
from src.agents.critique.api.services.rci_critique_service import critique_in_batches
from src.agents.critique.api.services.reformatter import reformat_to_investigation_plan_payload
from src.agents.critique.api.services.relevance_validation import validate_document_relevance
from src.agents.critique.api.services.llm_extraction import (
    convert_docx_to_pdf, extract_section_11, extract_section_12,
    extract_section_21, extract_section_22, merge_sections,
)
from src.agents.critique.api.services.xml_extraction import extract_all_sections
from src.llm.client import LLMClient
from src.utils.deps import get_prompt_registry

import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/critique', tags=['critique'])

llm = LLMClient()


_DEVIATION_REF_RE = re.compile(
    r"ODF/DR/|TW#|TW\s*#|\bDR/\d|\b[A-Z]{2,}/DR/\d{4}/\d+",
    re.IGNORECASE,
)
_RECURRENCE_CLAIM_RE = re.compile(
    r"(?:prior|earlier|previous(?:ly)?)\s+(?:event|deviation|investigation|corrective action|fix|action|"
    r"complaint|failure|problem|issue|occurrence)|recurr|previously[- ]corrected",
    re.IGNORECASE,
)

# Fixed leading phrase a regenerated recommendation uses when a previously accepted item is
# still not addressed by the current document (see rc_conclusion_system.txt/capa_system.txt).
# Matches Task Critique's identical marker (ds/src/agents/critique/graph/nodes.py) for a
# consistent investigator-facing wording across both features.
UNADDRESSED_MARKER = "Still unaddressed from the previous review."
_PREVIOUS_RECOMMENDATIONS_SENTINEL = "<<<PREVIOUS_RECOMMENDATIONS>>>"


def _parse_previous_recommendations(raw: str) -> List[str]:
    """previous_recommendations arrives as a JSON-encoded list of strings (see
    backend/backend/routers/rc_capa_critique.py's _call_critique_endpoint). Best-effort: any
    parse failure or wrong shape degrades to no previous recommendations rather than failing
    the request."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) and all(isinstance(r, str) for r in parsed) else []


def _render_previous_recommendations(previous: List[str]) -> str:
    return "\n".join(f"- {rec}" for rec in previous) if previous else "None."


def _with_previous_recommendations(system_prompt: str, previous: List[str]) -> str:
    """Fills in the PREVIOUSLY ACCEPTED RECOMMENDATIONS sentinel via a plain string replace
    (not .format()) since these prompt files contain literal JSON braces in their own output
    schema examples, which .format() would choke on."""
    return system_prompt.replace(_PREVIOUS_RECOMMENDATIONS_SENTINEL, _render_previous_recommendations(previous))


def _prioritize_and_cap(recommendations: List[str], limit: int = 5) -> List[str]:
    """Still-unaddressed carried-forward recommendations take priority over new ones within the
    cap — a code-side backstop in case the model doesn't fully honor the prompt's own ordering
    instruction. Stable sort preserves relative order within each group."""
    return sorted(recommendations, key=lambda r: not r.startswith(UNADDRESSED_MARKER))[:limit]


def _filter_recurrence_claims_without_citation(recommendations: List[str]) -> List[str]:
    return _prioritize_and_cap([
        rec for rec in recommendations
        if rec.startswith(UNADDRESSED_MARKER)
        or not (_RECURRENCE_CLAIM_RE.search(rec) and not _DEVIATION_REF_RE.search(rec))
    ])


def _suppress_recurrence_claims_without_citation(rc_result: RCConclusionCritiqueResponse) -> RCConclusionCritiqueResponse:
    """Drop any recommendation claiming a prior/recurring event was ignored unless it cites a
    concrete deviation/event reference. The prompt instructs the model not to raise this unless
    history genuinely revealed a prior event; this enforces that at the code layer for the mini
    model, which sometimes asserts recurrence language without a real citation. Carried-forward
    unaddressed items are exempt — they were already vetted on a previous attempt. Applied to
    both lists since the recurrence check (check 3) feeds rc_recommendations, but the filter
    itself is just text matching, so running it over impact_recommendations too is harmless."""
    rc_result.rc_recommendations = _filter_recurrence_claims_without_citation(rc_result.rc_recommendations)
    rc_result.impact_recommendations = _filter_recurrence_claims_without_citation(rc_result.impact_recommendations)
    return rc_result

def _cap_recommendations(capa_result: CAPACritiqueResponse) -> CAPACritiqueResponse:
    """Hard cap at 5 recommendations (still-unaddressed carried-forward ones first) in case the
    model over-generates despite the prompt limit. Also a code-side backstop for capa_status
    "missing"/"not_required": the prompt already tells the model not to propose recommendations
    in that case (there's no real CAPA to critique), but if it does anyway, force both lists
    empty here rather than trusting it — there is nothing to accept or reject when no CAPA was
    proposed or the report explicitly says none is needed."""
    if capa_result.capa_status in ("missing", "not_required"):
        capa_result.recommendations = []
        capa_result.previous_recommendation_checks = []
        return capa_result
    capa_result.recommendations = _prioritize_and_cap(capa_result.recommendations)
    return capa_result


def _format_capa_text(capa_overall_text: str, capa_items: List[dict]) -> str:
    """Plain-text rendering of the report's own CAPA section — the free text above the table
    plus each action row, verbatim from the document, no LLM involved."""
    lines = [capa_overall_text] if capa_overall_text else []
    for item in capa_items:
        line = item.get("description") or ""
        if not line:
            continue
        extras = [v for v in (item.get("responsibility"), item.get("due_date")) if v]
        if extras:
            line += " (" + ", ".join(extras) + ")"
        lines.append(line)
    return "\n".join(lines).strip()


async def _condense_section_text(label: str, text: str) -> str:
    """Shrinks the report's own verbatim section text to a 3-4 sentence plain-language
    summary for display (2026-08-20, per the user — the full verbatim section is too long
    for a dashboard summary card). Condensation only — condense_summary.txt forbids adding
    any fact not already in `text`; the source of truth stays the report's own text, this
    just makes it fit. Best-effort: a failure here must not fail the critique itself, it
    just falls back to showing the untouched verbatim text."""
    if not text.strip():
        return text
    try:
        condense_summary_system_prompt = get_prompt_registry().get("critique/condense_summary")
        return (await llm.chat(text, system=condense_summary_system_prompt)).strip()
    except Exception:
        logger.warning("Section summary condensation failed for %s", label, exc_info=True)
        return text


_EMPTY_SECTIONS: dict = {
    "problem_statement": "",
    "rc_conclusion_text": "",
    "is_repeat_occurrence": None,
    "investigation_summary": "",
    "impact_assessment_text": "",
    "impact_conclusion_text": "",
    "correction_remedial_text": "",
    "capa_overall_text": "",
    "capa_items": [],
}


async def _report_section_summaries(temp_path: Path) -> dict:
    """Returns the full extraction dict from extract_rci_report_sections (no LLM), plus
    two condensed plain-language summaries appended under "rc_summary"/"capa_summary"
    (via _condense_section_text) for the existing UI display. The raw "rc_conclusion_text"/
    "capa_overall_text"/"capa_items"/"is_repeat_occurrence"/"impact_assessment_text"/
    "correction_remedial_text" keys carry the report's own verbatim/structured content —
    callers use these for RCI Report generation, and "rc_summary"/"capa_summary" for the
    existing condensed display, never confusing the two. Best-effort: a report whose
    sections don't match the expected heading/table layout degrades to empty values rather
    than failing the critique."""
    try:
        sections = await asyncio.to_thread(extract_rci_report_sections, temp_path)
    except Exception:
        logger.warning("Non-LLM section extraction failed for %s", temp_path, exc_info=True)
        sections = dict(_EMPTY_SECTIONS)
    capa_text_for_condensing = _format_capa_text(sections["capa_overall_text"], sections["capa_items"])
    rc_summary, capa_summary = await asyncio.gather(
        _condense_section_text("rc_conclusion", sections["rc_conclusion_text"]),
        _condense_section_text("capa", capa_text_for_condensing),
    )
    return {**sections, "rc_summary": rc_summary, "capa_summary": capa_summary}


async def _save_and_extract(file: UploadFile) -> tuple[Path, str]:
    """Save upload to a temp file and return (temp_path, full_doc_text)."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = Path(tmp.name)
    full_doc_text = await asyncio.to_thread(extract_full_document_text, temp_path)
    return temp_path, full_doc_text


def _require_docx(file: UploadFile) -> None:
    suffix = (file.filename or "").rsplit(".", 1)[-1].lower()
    if suffix != "docx":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .docx files are supported",
        )


def _cleanup(temp_path: Path | None) -> None:
    if temp_path and temp_path.exists():
        try:
            temp_path.unlink()
        except Exception:
            logger.warning("Failed to clean up temp file: %s", temp_path)


# ── Existing endpoints ─────────────────────────────────────────────────────────

@router.post("/critique_rci_plan", tags=["critique"], response_model=CritiqueOutSchema)
async def critique_plan(event_type: str, RCI_data: CritiqueRCIRequest):
    data = RCI_data.model_dump()
    try:
        task_list = [TaskSchema(**item) for item in data["taskAssignments"]["data"]]
        critique_input = CritiqueInputSchema(
            problem_statement=[data["eventDescription"]["data"]["problemStatement"]],
            tasks=task_list,
            event_type=event_type,
        )
        llm_instance = LLMClient()
        registry = get_prompt_registry()
        strong_system_prompt = (
            registry.get("critique/critique_system")
            + "\nCRITICAL: Return tasks in EXACTLY the same order and same length as provided. "
              "Do NOT add, remove, or reorder tasks."
            + registry.get("guardrail")
        )
        return await critique_in_batches(
            llm=llm_instance,
            system_prompt=strong_system_prompt,
            user_prefix=registry.get("critique/critique_user"),
            data=critique_input,
            structure_model=CritiqueOutSchema,
            batch_size=5,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Critique generation failed")
        raise HTTPException(status_code=500, detail="Failed to generate critique")


@router.post(
    "/extract",
    tags=["extract"],
    response_class=JSONResponse,
    responses={
        200: {"description": "Extraction succeeded and returns FE-ready JSON."},
        415: {"description": "Unsupported media type (must be .docx or .pdf)."},
        500: {"description": "Internal server error."},
    },
)
async def extract(file: UploadFile = File(...)) -> JSONResponse:
    logger.info("Received extraction request for %s", file.filename)
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".docx", ".pdf"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .docx and .pdf files are supported",
        )

    temp_docx: Path | None = None
    temp_pdf: Path | None = None
    file_id: str | None = None
    try:
        if suffix == ".docx":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                shutil.copyfileobj(file.file, tmp)
                temp_docx = Path(tmp.name)
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                shutil.copyfileobj(file.file, tmp)
                temp_pdf = Path(tmp.name)

        if temp_docx:
            try:
                merged_data = await asyncio.to_thread(extract_all_sections, docx_path=temp_docx)
                ui_payload = reformat_to_investigation_plan_payload(merged_data)
            except Exception as e:
                logger.warning("DOCX extraction failed, falling back to LLM", exc_info=e)
                temp_pdf = await convert_docx_to_pdf(temp_docx)
                file_id = await llm.upload_file(temp_pdf)
                s11, s12, s21, s22 = await asyncio.gather(
                    extract_section_11(file_id), extract_section_12(file_id),
                    extract_section_21(file_id), extract_section_22(file_id),
                )
                merged_data = merge_sections(s11, s12, s21, s22)
                ui_payload = reformat_to_investigation_plan_payload(merged_data)
        else:
            file_id = await llm.upload_file(temp_pdf)
            s11, s12, s21, s22 = await asyncio.gather(
                extract_section_11(file_id), extract_section_12(file_id),
                extract_section_21(file_id), extract_section_22(file_id),
            )
            merged_data = merge_sections(s11, s12, s21, s22)
            ui_payload = reformat_to_investigation_plan_payload(merged_data)

        return JSONResponse(status_code=200, content={"filename": file.filename, "data": ui_payload})

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error during extraction")
        raise HTTPException(status_code=500, detail="Failed to process document")
    finally:
        await file.close()
        if file_id:
            try:
                await llm.delete_file(file_id)
            except Exception:
                logger.warning("Failed to delete uploaded LLM file: %s", file_id)
        for path in (temp_docx, temp_pdf):
            _cleanup(path)


# ── Task report critique endpoints ────────────────────────────────────────────

@router.post(
    "/critique-rc-conclusion",
    tags=["critique"],
    response_model=RCConclusionCritiqueResponse,
    summary="Critique only the RC conclusion section from a task report",
)
async def critique_rc_conclusion(
    event_type: str,
    problem_statement: str,
    file: UploadFile = File(..., description="Investigation task report (.docx)"),
    previous_recommendations: str = "",
) -> RCConclusionCritiqueResponse:
    _require_docx(file)
    temp_path = None
    try:
        temp_path, full_doc_text = await _save_and_extract(file)
        llm_instance = LLMClient()
        await validate_document_relevance(
            llm_instance,
            problem_statement=problem_statement,
            event_type=event_type,
            document_text=full_doc_text,
            document_label="task report",
        )
        user_prompt = f"Event Type: {event_type}\n\nFull Task Report:\n{full_doc_text}"

        registry = get_prompt_registry()
        result = await llm_instance.get_structured_response(
            system_prompt=_with_previous_recommendations(
                registry.get("critique/rc_conclusion_system"), _parse_previous_recommendations(previous_recommendations)
            ) + "\n" + registry.get("guardrail"),
            user_prompt=user_prompt,
            structure=RCConclusionCritiqueResponse,
            temperature=0,
        )
        sections = await _report_section_summaries(temp_path)
        result.rc_conclusion_text = sections["rc_summary"]
        result.rc_conclusion_text_raw = sections["rc_conclusion_text"]
        result.is_repeat_occurrence = sections["is_repeat_occurrence"]
        result.impact_assessment_text = sections["impact_assessment_text"]
        result.impact_conclusion_text = sections["impact_conclusion_text"]
        return _suppress_recurrence_claims_without_citation(result)
    except HTTPException:
        raise
    except Exception:
        logger.exception("RC conclusion critique failed for file: %s", file.filename)
        raise HTTPException(status_code=500, detail="Failed to critique RC conclusion")
    finally:
        await file.close()
        _cleanup(temp_path)


@router.post(
    "/critique-capa",
    tags=["critique"],
    response_model=CAPACritiqueResponse,
    summary="Critique only the CAPA section from a task report",
)
async def critique_capa(
    event_type: str,
    problem_statement: str,
    file: UploadFile = File(..., description="Investigation task report (.docx)"),
    previous_recommendations: str = "",
) -> CAPACritiqueResponse:
    _require_docx(file)
    temp_path = None
    try:
        temp_path, full_doc_text = await _save_and_extract(file)
        llm_instance = LLMClient()
        await validate_document_relevance(
            llm_instance,
            problem_statement=problem_statement,
            event_type=event_type,
            document_text=full_doc_text,
            document_label="task report",
        )
        user_prompt = f"Event Type: {event_type}\n\nFull Task Report:\n{full_doc_text}"

        registry = get_prompt_registry()
        result = await llm_instance.get_structured_response(
            system_prompt=_with_previous_recommendations(
                registry.get("critique/capa_system"), _parse_previous_recommendations(previous_recommendations)
            ) + "\n" + registry.get("guardrail"),
            user_prompt=user_prompt,
            structure=CAPACritiqueResponse,
            temperature=0,
        )
        if result.capa_status == "missing":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "No CAPA (Corrective and Preventive Action) section was found in the uploaded "
                    "report. Please reupload a report that includes a CAPA section."
                ),
            )
        sections = await _report_section_summaries(temp_path)
        result.capa_text = sections["capa_summary"]
        result.capa_text_raw = sections["capa_overall_text"]
        result.capa_items = [CAPAItemDetail(**item) for item in sections["capa_items"]]
        result.correction_remedial_text = sections["correction_remedial_text"]
        return _cap_recommendations(result)
    except HTTPException:
        raise
    except Exception:
        logger.exception("CAPA critique failed for file: %s", file.filename)
        raise HTTPException(status_code=500, detail="Failed to critique CAPA")
    finally:
        await file.close()
        _cleanup(temp_path)
