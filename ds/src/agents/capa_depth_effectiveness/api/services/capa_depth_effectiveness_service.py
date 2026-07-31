import asyncio
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

import pypdf
from fastapi import HTTPException, UploadFile, status
from pydantic import ValidationError

# Sole cross-module dependency of this package: reuse the existing docx -> markdown
# extraction utility rather than re-implementing it. Everything else in this module
# is independent of src.agents.critique.
from src.agents.critique.api.services.rci_report_extraction import extract_full_document_text

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

SUPPORTED_SUFFIXES = {"docx", "pdf"}

_SECTION_12_HEADING = re.compile(r"(?:\bcapa\s+)?effectiveness\s+check\s+plan\b", re.IGNORECASE)
_SECTION_13_HEADING = re.compile(r"list\s+of\s+(?:annexure|attachment)s?", re.IGNORECASE)
_SECTION_12_REDACTION_NOTE = (
    "[Section 12 — Effectiveness Check Plan — has been removed from this excerpt. "
    "Do not reference, assume, or reconstruct its content.]"
)


def require_supported_file(file: UploadFile) -> str:
    """Validate the upload is .docx or .pdf and return the lowercase suffix."""
    suffix = (file.filename or "").rsplit(".", 1)[-1].lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .docx and .pdf files are supported",
        )
    return suffix


async def save_upload(file: UploadFile, suffix: str) -> Path:
    """Save the upload to a temp file with the correct suffix (no extraction)."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix}") as tmp:
        shutil.copyfileobj(file.file, tmp)
        return Path(tmp.name)


async def extract_docx_text(temp_path: Path) -> str:
    """Convert a docx to clean markdown text (reuses critique's extraction utility)."""
    return await asyncio.to_thread(extract_full_document_text, temp_path)


async def extract_pdf_text(temp_path: Path) -> str:
    """Extract plain text from a PDF locally via pypdf.

    Used ONLY to produce a section-12-redacted excerpt for the generated_plan
    call (see strip_section_12). The capa_depth and extraction/rule-critique
    calls keep reading the native PDF file directly via file upload, unchanged
    — this local extraction path exists solely so generated_plan can be given
    a version of the report with no way to see section 12's real content.
    """
    def _extract() -> str:
        reader = pypdf.PdfReader(temp_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    return await asyncio.to_thread(_extract)


def strip_section_12(text: str) -> str:
    """Remove the Effectiveness Check Plan (section 12) content from report text.

    Prompt instructions alone ("don't read or copy section 12") proved
    insufficient: a live investigation found generated_plan's monitoring
    duration consistently echoing the report's real value whenever section 12
    was present, most likely because the same LLM call had already written
    that real value into `extraction` moments earlier in its own output.
    Physically removing section 12 from the text this call reads is the only
    way to make independence a guarantee rather than an instruction.

    Uses the LAST occurrence of the section-12 heading (earlier occurrences
    are typically a table-of-contents reference, not the real section) and
    the next "List of Annexures/Attachments" heading as the closing boundary,
    falling back to end-of-text if no closing heading is found.
    """
    headings = list(_SECTION_12_HEADING.finditer(text))
    if not headings:
        return text

    start = headings[-1].start()
    closing = _SECTION_13_HEADING.search(text, pos=headings[-1].end())
    end = closing.start() if closing else len(text)

    return text[:start] + _SECTION_12_REDACTION_NOTE + text[end:]


def cleanup(temp_path: Path | None) -> None:
    if temp_path and temp_path.exists():
        try:
            temp_path.unlink()
        except Exception:
            logger.warning("Failed to clean up temp file: %s", temp_path)


async def call_with_retry(
    call: Callable[[], Awaitable[_T]],
    *,
    max_attempts: int = 3,
    label: str = "structured response",
) -> _T:
    """Retry a structured-response call when a Pydantic @model_validator rejects an
    internally-inconsistent response (e.g. kpi duplicating acceptance_criteria, or a
    rule4_classification/critique mismatch).

    OpenAI's structured-outputs JSON schema only constrains per-field shape (types,
    enums, required keys); it cannot express cross-field consistency. That's enforced
    client-side by our @model_validator(mode="after") hooks when the SDK parses the
    response into our Pydantic model (via model_validate_json, which does run custom
    validators) — but the SDK itself has no retry loop, so a validator's raised
    ValidationError would otherwise propagate straight out as a hard failure with no
    second attempt. This wrapper is that retry loop.
    """
    last_exc: ValidationError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await call()
        except ValidationError as exc:
            last_exc = exc
            logger.warning(
                "%s: failed internal-consistency validation on attempt %d/%d: %s",
                label, attempt, max_attempts, exc,
            )
    assert last_exc is not None
    raise last_exc
