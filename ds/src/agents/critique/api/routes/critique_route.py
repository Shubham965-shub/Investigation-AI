import re
import shutil
import tempfile
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, File, UploadFile, status
from fastapi.responses import JSONResponse

from src.agents.critique.api.schemas import (
    CritiqueInputSchema, CritiqueOutSchema, TaskSchema, CritiqueRCIRequest,
    RCConclusionCritiqueResponse, CAPACritiqueResponse, RCIReportCritiqueResponse,
)
from src.agents.critique.api.services.rci_report_extraction import extract_full_document_text
from src.agents.critique.api.services.rci_critique_service import critique_in_batches
from src.agents.critique.api.services.reformatter import reformat_to_investigation_plan_payload
from src.agents.critique.api.services.llm_extraction import (
    convert_docx_to_pdf, extract_section_11, extract_section_12,
    extract_section_21, extract_section_22, merge_sections,
)
from src.agents.critique.api.services.xml_extraction import extract_all_sections
from src.llm.client import LLMClient
from config.settings import settings

import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/critique', tags=['critique'])


def _load_prompt(filename: str) -> str:
    if filename == "guardrail.txt":
        return (settings.PROMPTS_DIR / filename).read_text(encoding="utf-8")
    return (settings.PROMPTS_DIR / "critique" / filename).read_text(encoding="utf-8")


guard_rail_text = _load_prompt("guardrail.txt")
critique_system_prompt = _load_prompt("critique_system.txt")
critique_user_prompt = _load_prompt("critique_user.txt")
rc_conclusion_system_prompt = _load_prompt("rc_conclusion_system.txt")
capa_system_prompt = _load_prompt("capa_system.txt")

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

def _suppress_recurrence_claims_without_citation(rc_result: RCConclusionCritiqueResponse) -> RCConclusionCritiqueResponse:
    """Drop any recommendation claiming a prior/recurring event was ignored unless it cites a
    concrete deviation/event reference. The prompt instructs the model not to raise this unless
    history genuinely revealed a prior event; this enforces that at the code layer for the mini
    model, which sometimes asserts recurrence language without a real citation."""
    rc_result.recommendations = [
        rec for rec in rc_result.recommendations
        if not (_RECURRENCE_CLAIM_RE.search(rec) and not _DEVIATION_REF_RE.search(rec))
    ]
    return rc_result


def _extract_problem_statement(full_doc_text: str) -> str:
    """Pull the problem statement text from the full markdown document."""
    m = re.search(
        r"problem\s+(?:statement|description)[^\n]*\n+(.+?)(?=\n\n|\Z)",
        full_doc_text, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).strip()
    m = re.search(
        r"problem\s+(?:statement|description)\s*[:\-]\s*(.+)",
        full_doc_text, re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


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
        strong_system_prompt = (
            critique_system_prompt
            + "\nCRITICAL: Return tasks in EXACTLY the same order and same length as provided. "
              "Do NOT add, remove, or reorder tasks."
            + guard_rail_text
        )
        return await critique_in_batches(
            llm=llm_instance,
            system_prompt=strong_system_prompt,
            user_prefix=critique_user_prompt,
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
    "/critique-rc-conclusion-and-capa",
    tags=["critique"],
    response_model=RCIReportCritiqueResponse,
    summary="Critique RC conclusion and CAPA from a task report (full document)",
)
async def critique_rc_conclusion_and_capa(
    event_type: str,
    file: UploadFile = File(..., description="Investigation task report (.docx)"),
) -> RCIReportCritiqueResponse:
    _require_docx(file)
    temp_path = None
    try:
        temp_path, full_doc_text = await _save_and_extract(file)
        user_prompt = f"Event Type: {event_type}\n\nFull Task Report:\n{full_doc_text}"

        llm_instance = LLMClient()
        rc_result, capa_result = await asyncio.gather(
            llm_instance.get_structured_response(
                system_prompt=rc_conclusion_system_prompt + "\n" + guard_rail_text,
                user_prompt=user_prompt,
                structure=RCConclusionCritiqueResponse,
            ),
            llm_instance.get_structured_response(
                system_prompt=capa_system_prompt + "\n" + guard_rail_text,
                user_prompt=user_prompt,
                structure=CAPACritiqueResponse,
            ),
        )
        return RCIReportCritiqueResponse(
            problem_statement=_extract_problem_statement(full_doc_text),
            rc_conclusion=_suppress_recurrence_claims_without_citation(rc_result),
            capa=capa_result,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Task report analysis failed for file: %s", file.filename)
        raise HTTPException(status_code=500, detail="Failed to analyse task report")
    finally:
        await file.close()
        _cleanup(temp_path)


@router.post(
    "/critique-rc-conclusion",
    tags=["critique"],
    response_model=RCConclusionCritiqueResponse,
    summary="Critique only the RC conclusion section from a task report",
)
async def critique_rc_conclusion(
    event_type: str,
    file: UploadFile = File(..., description="Investigation task report (.docx)"),
) -> RCConclusionCritiqueResponse:
    _require_docx(file)
    temp_path = None
    try:
        temp_path, full_doc_text = await _save_and_extract(file)
        user_prompt = f"Event Type: {event_type}\n\nFull Task Report:\n{full_doc_text}"

        llm_instance = LLMClient()
        result = await llm_instance.get_structured_response(
            system_prompt=rc_conclusion_system_prompt + "\n" + guard_rail_text,
            user_prompt=user_prompt,
            structure=RCConclusionCritiqueResponse,
        )
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
    file: UploadFile = File(..., description="Investigation task report (.docx)"),
) -> CAPACritiqueResponse:
    _require_docx(file)
    temp_path = None
    try:
        temp_path, full_doc_text = await _save_and_extract(file)
        user_prompt = f"Event Type: {event_type}\n\nFull Task Report:\n{full_doc_text}"

        llm_instance = LLMClient()
        return await llm_instance.get_structured_response(
            system_prompt=capa_system_prompt + "\n" + guard_rail_text,
            user_prompt=user_prompt,
            structure=CAPACritiqueResponse,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("CAPA critique failed for file: %s", file.filename)
        raise HTTPException(status_code=500, detail="Failed to critique CAPA")
    finally:
        await file.close()
        _cleanup(temp_path)
