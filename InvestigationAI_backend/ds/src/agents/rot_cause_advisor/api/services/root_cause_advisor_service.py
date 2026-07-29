import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, List

from fastapi import HTTPException, UploadFile, status

from src.config.settings import settings
from src.llm.client import LLMClient
from agents.rot_cause_advisor.api.schemas import rootCauseAdvisoryResponse

logger = logging.getLogger(__name__)

SUPPORTED_FILE_SUFFIXES = {".pdf", ".docx"}

ROOT_CAUSE_CATEGORIES = [
    "man",
    "machine",
    "material",
    "method",
    "measurement",
    "milieu",
]

def _load_prompt(filename: str, subfolder: str | None = None) -> str:
    prompt_dir = settings.PROMPTS_DIR
    if subfolder:
        prompt_dir = prompt_dir / subfolder
    prompt_path = prompt_dir / filename
    return prompt_path.read_text(encoding="utf-8")


ROOT_CAUSE_ADVISOR_SYSTEM_PROMPT = _load_prompt(
    "root_cause_advisor_system.txt",
    subfolder="rca",
)

ROOT_CAUSE_ADVISOR_USER_PROMPT = _load_prompt(
    "root_cause_advisor_user.txt",
    subfolder="rca",
)

GUARDRAIL_TEXT = _load_prompt("guardrail.txt")


def _build_advisor_prompt(event_type: str) -> str:
    """
    Builds a file-based prompt.
    We intentionally instruct the model to read from the uploaded file
    and return a top-level JSON array.
    """
    prompt = ROOT_CAUSE_ADVISOR_USER_PROMPT
    prompt = prompt.replace("__EVENT_TYPE__", event_type)

    prompt = prompt + (
            "Use the uploaded investigation document as the only source of truth. "
            "Return a top-level JSON array with exactly 6 objects, one per category. "
            "Do not wrap the array in another object."
        )
    return prompt


async def generate_root_cause_advice(
    event_type: str,
    file: UploadFile,
    llm: LLMClient,
) -> List[rootCauseAdvisoryResponse]:
    """
    Accepts a DOCX or PDF file, uploads it directly to the LLM,
    asks for raw JSON output, then validates it into List[RootCauseCategory].

    No DOCX -> PDF conversion is performed.
    """
    filename = (file.filename or "").strip()
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_FILE_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .docx and .pdf files are supported.",
        )

    temp_file: Path | None = None
    file_id: str | None = None

    try:
        logger.info(
            f"Received root cause advisor request: filename={filename}, suffix={suffix}, event_type={event_type}",
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_file = Path(tmp.name)

        logger.info(f"Saved uploaded file to temporary path: {temp_file}")

        if not temp_file.exists():
            raise RuntimeError("Failed to save uploaded file before LLM upload.")

        file_id = await llm.upload_file(temp_file)
        logger.info(f"Uploaded file to LLM successfully: file_id={file_id}")

        user_prompt = _build_advisor_prompt(event_type)
        system_prompt = ROOT_CAUSE_ADVISOR_SYSTEM_PROMPT + "\n" + GUARDRAIL_TEXT

        logger.info("Requesting raw JSON root cause advisor response from LLM")

        raw = await llm.get_structured_response_from_file(
            file_id=file_id,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            structure=rootCauseAdvisoryResponse
        )

        logger.info(f"Received raw JSON response from LLM")

        return raw

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(
            f"Root cause advisor generation failed for uploaded file: filename={e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate root cause advice from uploaded document.",
        )

    finally:
        try:
            await file.close()
        except Exception:
            logger.warning(f"Failed to close uploaded file: {filename}")

        if file_id:
            try:
                await llm.delete_file(file_id)
                logger.info(f"Deleted uploaded LLM file successfully: {file_id}")
            except Exception:
                logger.warning(f"Failed to delete uploaded LLM file: {file_id}")

        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
                logger.info(f"Deleted temporary file: {temp_file}")
            except Exception:
                logger.warning(f"Failed to cleanup temp file: {temp_file}")