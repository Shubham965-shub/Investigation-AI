from pathlib import Path
import shutil
import tempfile
import asyncio
from fastapi import APIRouter, HTTPException, File, UploadFile, status
from fastapi.responses import JSONResponse
from src.agents.critique.api.services.extraction import extract_rci_plan
from src.agents.critique.api.schemas import (
    CritiqueInputSchema, CritiqueOutSchema, TaskSchema, CritiqueRCIRequest,
    RCConclusionCritiqueRequest, RCConclusionCritiqueResponse, RuleCritique,
    CAPACritiqueRequest, CAPACritiqueResponse, CAPAItemDetail,
    RCIReportCritiqueResponse,
)
from src.agents.critique.api.services.rci_report_extraction import extract_rci_report_sections
from src.agents.critique.api.services.rci_critique_service import critique_in_batches
from src.llm.client import LLMClient
from config.settings import settings
from src.agents.critique.api.services.reformatter import reformat_to_investigation_plan_payload
from src.agents.critique.api.services.llm_extraction import (
     convert_docx_to_pdf, extract_section_11, extract_section_12,
     extract_section_21, extract_section_22, merge_sections
)
from src.agents.critique.api.services.xml_extraction import (
     extract_all_sections
)



from docx import Document


import logging

def _load_prompt(filename: str) -> str:
    """Load a prompt template from the centralized prompts directory."""
    if filename == "guardrail.txt":
        prompt_path = settings.PROMPTS_DIR / filename
        return prompt_path.read_text(encoding="utf-8")
    prompt_path = settings.PROMPTS_DIR / "critique" / filename
    return prompt_path.read_text(encoding="utf-8")

guard_rail_text = _load_prompt("guardrail.txt")
critique_system_prompt = _load_prompt("critique_system.txt")
critique_user_prompt = _load_prompt("critique_user.txt")
rc_conclusion_system_prompt = _load_prompt("rc_conclusion_system.txt")
capa_proposal_system_prompt = _load_prompt("capa_proposal_system.txt")

llm = LLMClient()

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/critique', tags=['critique'])

@router.post(
    "/critique_rci_plan",
    tags=["critique"],
    response_model=CritiqueOutSchema,
)
async def critique_plan(
    event_type: str,
    RCI_data: CritiqueRCIRequest
):
    data = RCI_data.model_dump()
    try:
        task_list = [
            TaskSchema(**item)
            for item in data["taskAssignments"]["data"]
        ]


        critique_input = CritiqueInputSchema(
            problem_statement = [data["eventDescription"]["data"]["problemStatement"]],
            tasks = task_list,
            event_type=event_type,
        )

        llm = LLMClient()
        strong_system_prompt = (
            critique_system_prompt
            + "\nCRITICAL: Return tasks in EXACTLY the same order and same length as provided. "
              "Do NOT add, remove, or reorder tasks."
            + guard_rail_text
        )

        result = await critique_in_batches(
            llm=llm,
            system_prompt=strong_system_prompt,
            user_prefix=critique_user_prompt,
            data=critique_input,
            structure_model=CritiqueOutSchema,
            batch_size=5,
        )
        return result

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Critique generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate critique",
        )


@router.post(
    "/extract",
    tags=["extract"],
    response_class=JSONResponse,
    responses={
        200: {"description": "Extraction succeeded and returns FE-ready JSON."},
        400: {"description": "Bad request or extraction error."},
        415: {"description": "Unsupported media type (must be .docx)."},
        500: {"description": "Internal server error."},
    },
)

async def extract(file: UploadFile = File(...)) -> JSONResponse:
    """
    Accept a DOCX or PDF and return FE-ready JSON.
    Hybrid local + LLM extraction is handled in the service layer.
    """
    logger.info(f"received extraction request for {file.filename}")
    suffix = Path(file.filename).suffix.lower()

    if suffix not in {".docx", ".pdf"}:
            # raise HTTPException(
            #     status_code=400,
            #     detail="Only .docx and .pdf files are supported"
            # )

            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only .docx and .pdf files are supported"
            )


    temp_docx: Path | None = None
    temp_pdf: Path | None = None
    file_id: str | None = None
    try:
        logger.info(f"Suffix {suffix}")
        logger.info(f"temp_docx {temp_docx}")
        if suffix == ".docx":
            # 1. Save DOCX
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                shutil.copyfileobj(file.file, tmp)
                temp_docx = Path(tmp.name)

            # # 2. Convert DOCX -> PDF (Docker LibreOffice)
            # temp_pdf = await convert_docx_to_pdf(temp_docx)


        else:
            # PDF uploaded → save directly
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            shutil.copyfileobj(file.file, tmp)
                            temp_pdf = Path(tmp.name)



        logger.info(f"Suffix {suffix}")
        logger.info(f"temp_docx {temp_docx}")
        if temp_docx:
            try:
                merged_data = await asyncio.to_thread(
                    extract_all_sections, docx_path=temp_docx
                )

                ui_payload = reformat_to_investigation_plan_payload(merged_data)

            except Exception as e:
                logger.warning(
                    "DOCX extraction/reformat failed, falling back to LLM extraction",
                    exc_info=e
                )
                temp_pdf = await convert_docx_to_pdf(temp_docx)
                file_id = await llm.upload_file(temp_pdf)

                s11, s12, s21, s22 = await asyncio.gather(
                    extract_section_11(file_id),
                    extract_section_12(file_id),
                    extract_section_21(file_id),
                    extract_section_22(file_id),
                )

                merged_data = merge_sections(s11, s12, s21, s22)
                ui_payload = reformat_to_investigation_plan_payload(merged_data)

        else:
            file_id = await llm.upload_file(temp_pdf)

            s11, s12, s21, s22 = await asyncio.gather(
                extract_section_11(file_id),
                extract_section_12(file_id),
                extract_section_21(file_id),
                extract_section_22(file_id),
            )

            merged_data = merge_sections(s11, s12, s21, s22)
            ui_payload = reformat_to_investigation_plan_payload(merged_data)


        return JSONResponse(
                    status_code=200,
                    content={
                        "filename": file.filename,
                        "data": ui_payload,
                    },
                )


    except HTTPException:
            raise

    except Exception as e:
        # ❌ Unexpected failure
        logger.exception("Unhandled error during RCI extraction")
        raise HTTPException(
            status_code=500,
            detail="Failed to process RCI Plan document",
        )

    finally:
        await file.close()

        if file_id:
                    try:
                        await llm.delete_file(file_id)
                    except Exception:
                        logger.warning(f"Failed to delete uploaded LLM file: {file_id}")


        for path in (temp_docx, temp_pdf):
            if path and path.exists():
                try:
                    path.unlink()
                except Exception:
                    logger.warning(f"Failed to cleanup temp file: {path}")


@router.post(
    "/critique_rc_conclusion",
    tags=["critique"],
    response_model=RCConclusionCritiqueResponse,
    summary="Critique the Root Cause Conclusion section (Section 8) of an RCI report",
)
async def critique_rc_conclusion(body: RCConclusionCritiqueRequest):
    """
    Evaluates the RC conclusion text against 4 rules:
    1. Evidence-Based Substantiation
    2. Logical Traceability and Linkage
    3. Historical and Recurrence Assessment
    4. Root Cause and Impact Linkage
    """
    user_prompt = _build_rc_user_prompt(body)

    try:
        llm_instance = LLMClient()
        result: RCConclusionCritiqueResponse = await llm_instance.get_structured_response(
            system_prompt=rc_conclusion_system_prompt + "\n" + guard_rail_text,
            user_prompt=user_prompt,
            structure=RCConclusionCritiqueResponse,
        )
        return result
    except Exception as exc:
        logger.exception("RC conclusion critique failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate RC conclusion critique",
        )


@router.post(
    "/critique_capa_proposal",
    tags=["critique"],
    response_model=CAPACritiqueResponse,
    summary="Critique the CAPA proposal section (Section 12) of an RCI report",
)
async def critique_capa_proposal(body: CAPACritiqueRequest):
    """
    Evaluates the CAPA proposal against 4 rules:
    1. Root Cause Alignment
    2. Consistency with Problem and Findings
    3. Corrective and Preventive Completeness
    4. Gap and Linkage Integrity
    """
    user_prompt = _build_capa_user_prompt(body)

    try:
        llm_instance = LLMClient()
        result: CAPACritiqueResponse = await llm_instance.get_structured_response(
            system_prompt=capa_proposal_system_prompt + "\n" + guard_rail_text,
            user_prompt=user_prompt,
            structure=CAPACritiqueResponse,
        )
        return result
    except Exception as exc:
        logger.exception("CAPA proposal critique failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate CAPA proposal critique",
        )


def _build_rc_user_prompt(body: RCConclusionCritiqueRequest) -> str:
    repeat_str = (
        "Yes" if body.is_repeat_occurrence
        else "No" if body.is_repeat_occurrence is False
        else "Not specified"
    )
    return "\n".join([
        f"Event Type: {body.event_type}",
        f"Problem Statement: {body.problem_statement}",
        "",
        f"Investigation Summary (what tasks found):\n{body.investigation_summary}",
        "",
        f"Repeat Occurrence: {repeat_str}",
        "",
        f"RC Conclusion Text (Section 8):\n{body.rc_conclusion_text}",
    ])


def _build_capa_user_prompt(body: CAPACritiqueRequest) -> str:
    capa_items_text = "\n".join(
        "- Description: " + item.description
        + (" | Responsibility: " + item.responsibility if item.responsibility else "")
        + (" | Due Date: " + item.due_date if item.due_date else "")
        for item in body.capa_items
    ) or "No CAPA actions specified."

    parts = [
        f"Event Type: {body.event_type}",
        f"Problem Statement: {body.problem_statement}",
        "",
        f"RC Conclusion (Section 8):\n{body.rc_conclusion_text}",
        "",
        f"Investigation Summary (gaps identified):\n{body.investigation_summary}",
        "",
        "CAPA Proposal (Section 12):",
    ]
    if body.capa_overall_text:
        parts.append(body.capa_overall_text)
        parts.append("")
    parts.append(f"CAPA Actions:\n{capa_items_text}")
    return "\n".join(parts)


@router.post(
    "/analyse-rci-report",
    tags=["critique"],
    response_model=RCIReportCritiqueResponse,
    summary="Extract and critique RC conclusion (Section 8) and CAPA (Section 12) from an RCI report",
)
async def analyse_rci_report(
    event_type: str,
    file: UploadFile = File(..., description="Completed RCI report (.docx)"),
) -> RCIReportCritiqueResponse:
    """
    Accepts a completed RCI report .docx, extracts Section 8 (RC Conclusion) and
    Section 12 (CAPA), and critiques both in parallel.
    """
    suffix = (file.filename or "").rsplit(".", 1)[-1].lower()
    if suffix != "docx":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .docx files are supported",
        )

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_path = Path(tmp.name)

        extracted = await asyncio.to_thread(extract_rci_report_sections, temp_path)

        rc_request = RCConclusionCritiqueRequest(
            event_type=event_type,
            problem_statement=extracted["problem_statement"],
            investigation_summary=extracted["investigation_summary"],
            rc_conclusion_text=extracted["rc_conclusion_text"],
            is_repeat_occurrence=extracted["is_repeat_occurrence"],
        )
        capa_request = CAPACritiqueRequest(
            event_type=event_type,
            problem_statement=extracted["problem_statement"],
            rc_conclusion_text=extracted["rc_conclusion_text"],
            investigation_summary=extracted["investigation_summary"],
            capa_items=[CAPAItemDetail(**item) for item in extracted["capa_items"]],
            capa_overall_text=extracted["capa_overall_text"] or None,
        )

        llm_instance = LLMClient()
        rc_result, capa_result = await asyncio.gather(
            llm_instance.get_structured_response(
                system_prompt=rc_conclusion_system_prompt + "\n" + guard_rail_text,
                user_prompt=_build_rc_user_prompt(rc_request),
                structure=RCConclusionCritiqueResponse,
            ),
            llm_instance.get_structured_response(
                system_prompt=capa_proposal_system_prompt + "\n" + guard_rail_text,
                user_prompt=_build_capa_user_prompt(capa_request),
                structure=CAPACritiqueResponse,
            ),
        )

        return RCIReportCritiqueResponse(
            problem_statement=extracted["problem_statement"],
            rc_conclusion=rc_result,
            capa=capa_result,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("RCI report analysis failed for file: %s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyse RCI report",
        )
    finally:
        await file.close()
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                logger.warning("Failed to clean up temp file: %s", temp_path)
