"""API routes for rubric-based report scoring."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from src.agents.scoring.api.schemas import (
    ScoringReportResponse,
    SectionScore,
    SectionScoreRequest,
)
from src.agents.scoring.rubric.rubric_config import ALL_SECTION_KEYS
from src.agents.scoring.services.persistence import persist_score
from src.agents.scoring.services.scoring_service import score_report_from_bytes, score_single_section

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/score", tags=["scoring"])

_ALLOWED_SUFFIXES = {".docx", ".pdf"}
_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _score_upload(file: UploadFile, event_type: Optional[str]) -> ScoringReportResponse:
    """Validate the upload, score it, check a section was found, and persist. Shared
    by the JSON and .xlsx report endpoints. Raises HTTPException on 415/422."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .docx and .pdf files are supported",
        )
    data = await file.read()
    response = await score_report_from_bytes(
        data, file.filename or f"upload{suffix}", event_type_override=event_type
    )
    if not response.detected_sections:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No scoreable section (Task Report / RC / Impact / CAPA) was found in the document.",
        )
    await _persist_best_effort(file.filename, response)
    return response


@router.post(
    "/report",
    response_model=ScoringReportResponse,
    summary="Score an investigation report (consolidated or single-section) against the rubrics",
    description=(
        "Upload a completed investigation report (.docx or .pdf). The service auto-detects which of "
        "the four scoreable sections are present — Task Report, Root Cause, Impact, CAPA — scores each "
        "present section against its marking checklist, and returns the two report scores, the "
        "consolidated final percentage, and the per-checkpoint rationale behind every score."
    ),
)
async def score_report_endpoint(
    file: UploadFile = File(..., description="Completed investigation report (.docx or .pdf)"),
    event_type: Optional[str] = Form(
        None, description="Optional override: Deviation | OOS | OOT | Market Complaint"
    ),
) -> ScoringReportResponse:
    try:
        return await _score_upload(file, event_type)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Report scoring failed for file: %s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to score report",
        )
    finally:
        await file.close()


@router.post(
    "/report/xlsx",
    summary="Score a report and return the full breakdown as an .xlsx workbook",
    description=(
        "Same scoring as /score/report, but returns a formatted Excel workbook "
        "(Summary, Task Report, IQ Score sheets) suitable for review / handover."
    ),
    response_class=Response,
)
async def score_report_xlsx_endpoint(
    file: UploadFile = File(..., description="Completed investigation report (.docx or .pdf)"),
    event_type: Optional[str] = Form(None),
) -> Response:
    try:
        # Imported lazily — the export module is kept out of version control, so
        # the rest of the service works even where it isn't deployed.
        try:
            from src.agents.scoring.export.xlsx_export import build_scoring_xlsx
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="XLSX export is not available in this deployment.",
            )
        response = await _score_upload(file, event_type)
        workbook = build_scoring_xlsx(response)
        stem = Path(file.filename).stem if file.filename else "report"
        return Response(
            content=workbook,
            media_type=_XLSX_MEDIA,
            headers={"Content-Disposition": f'attachment; filename="{stem}_score.xlsx"'},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Report scoring (xlsx) failed for file: %s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to score report",
        )
    finally:
        await file.close()


@router.post(
    "/section",
    response_model=SectionScore,
    summary="Score a single already-extracted section's text against its rubric",
)
async def score_section_endpoint(body: SectionScoreRequest) -> SectionScore:
    if body.section not in ALL_SECTION_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"section must be one of {list(ALL_SECTION_KEYS)}",
        )
    if not body.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="text must not be empty"
        )
    try:
        return await score_single_section(body)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Section scoring failed for section: %s", body.section)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to score section",
        )


async def _persist_best_effort(filename: Optional[str], response: ScoringReportResponse) -> None:
    try:
        from src.utils.deps import get_db_pool

        pool = await get_db_pool()
    except Exception:
        return  # pool not initialised (e.g. tests) — skip silently
    await persist_score(pool, filename, response)
