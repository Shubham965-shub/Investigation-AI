import asyncio
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from src.agents.capa_depth_effectiveness.api.schemas import (
    CAPADepthClassification,
    CAPADepthEffectivenessResponse,
    EffectivenessCheckExtractionAndCritique,
    EffectivenessCheckResult,
    GeneratedEffectivenessPlan,
)
from src.agents.capa_depth_effectiveness.api.services.capa_depth_effectiveness_service import (
    call_with_retry,
    cleanup,
    extract_docx_text,
    extract_pdf_text,
    require_supported_file,
    save_upload,
    strip_section_12,
)
from src.llm.client import LLMClient
from src.utils.deps import get_prompt_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/capa-depth-effectiveness", tags=["capa-depth-effectiveness"])


@router.post(
    "/analyse",
    response_model=CAPADepthEffectivenessResponse,
    summary=(
        "Classify CAPA depth against the CAPA Hierarchy (SOP GQA/070) and check the "
        "CAPA Effectiveness Check Plan against the mandatory rules in SOP GQA/008, "
        "from a completed RCI report (.docx or .pdf)."
    ),
)
async def analyse_capa_depth_effectiveness(
    event_type: str,
    file: UploadFile = File(..., description="Completed RCI report (.docx or .pdf)"),
) -> CAPADepthEffectivenessResponse:
    suffix = require_supported_file(file)
    temp_path = None
    file_id = None
    llm_instance = LLMClient()
    registry = get_prompt_registry()
    guard_rail_text = registry.get("guardrail")
    capa_depth_system_prompt = registry.get("capa_depth_effectiveness/capa_depth_system")
    effectiveness_check_system_prompt = registry.get("capa_depth_effectiveness/effectiveness_check_system")
    generated_plan_system_prompt = registry.get("capa_depth_effectiveness/generated_effectiveness_plan_system")
    try:
        temp_path = await save_upload(file, suffix)
        user_prompt_prefix = f"Event Type: {event_type}"

        if suffix == "docx":
            full_doc_text = await extract_docx_text(temp_path)
            redacted_doc_text = strip_section_12(full_doc_text)
            user_prompt = f"{user_prompt_prefix}\n\nFull RCI Report:\n{full_doc_text}"
            generated_plan_user_prompt = (
                f"{user_prompt_prefix}\n\nRCI Report excerpt:\n{redacted_doc_text}"
            )

            depth_result, extraction_critique_result, generated_plan_result = await asyncio.gather(
                call_with_retry(
                    lambda: llm_instance.get_structured_response(
                        system_prompt=capa_depth_system_prompt + "\n" + guard_rail_text,
                        user_prompt=user_prompt,
                        structure=CAPADepthClassification,
                    ),
                    label="capa_depth",
                ),
                call_with_retry(
                    lambda: llm_instance.get_structured_response(
                        system_prompt=effectiveness_check_system_prompt + "\n" + guard_rail_text,
                        user_prompt=user_prompt,
                        structure=EffectivenessCheckExtractionAndCritique,
                    ),
                    label="effectiveness_check",
                ),
                call_with_retry(
                    lambda: llm_instance.get_structured_response(
                        system_prompt=generated_plan_system_prompt + "\n" + guard_rail_text,
                        user_prompt=generated_plan_user_prompt,
                        structure=GeneratedEffectivenessPlan,
                    ),
                    label="generated_plan",
                ),
            )
        else:  # pdf — no local extraction for capa_depth/extraction_critique; the model
            # reads the uploaded file natively for those two calls. generated_plan is the
            # one exception: it needs a section-12-redacted excerpt, which requires local
            # text extraction (pypdf) purely to produce that redacted text — see
            # strip_section_12 in capa_depth_effectiveness_service.py.
            file_id = await llm_instance.upload_file(temp_path)
            user_prompt = f"{user_prompt_prefix}\n\nThe full RCI report is attached as a file."
            pdf_text = await extract_pdf_text(temp_path)
            redacted_doc_text = strip_section_12(pdf_text)
            generated_plan_user_prompt = (
                f"{user_prompt_prefix}\n\nRCI Report excerpt:\n{redacted_doc_text}"
            )

            depth_result, extraction_critique_result, generated_plan_result = await asyncio.gather(
                call_with_retry(
                    lambda: llm_instance.get_structured_response_from_file(
                        file_id=file_id,
                        system_prompt=capa_depth_system_prompt + "\n" + guard_rail_text,
                        user_prompt=user_prompt,
                        structure=CAPADepthClassification,
                    ),
                    label="capa_depth",
                ),
                call_with_retry(
                    lambda: llm_instance.get_structured_response_from_file(
                        file_id=file_id,
                        system_prompt=effectiveness_check_system_prompt + "\n" + guard_rail_text,
                        user_prompt=user_prompt,
                        structure=EffectivenessCheckExtractionAndCritique,
                    ),
                    label="effectiveness_check",
                ),
                call_with_retry(
                    lambda: llm_instance.get_structured_response(
                        system_prompt=generated_plan_system_prompt + "\n" + guard_rail_text,
                        user_prompt=generated_plan_user_prompt,
                        structure=GeneratedEffectivenessPlan,
                    ),
                    label="generated_plan",
                ),
            )

        ec_result = EffectivenessCheckResult(
            extraction=extraction_critique_result.extraction,
            rule_critiques=extraction_critique_result.rule_critiques,
            generated_plan=generated_plan_result,
        )

        return CAPADepthEffectivenessResponse(
            event_type=event_type,
            capa_depth=depth_result,
            effectiveness_check=ec_result,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "CAPA depth/effectiveness analysis failed for file: %s", file.filename
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to analyse CAPA depth and effectiveness check plan",
        )
    finally:
        await file.close()
        cleanup(temp_path)
        if file_id:
            await llm_instance.delete_file(file_id)
