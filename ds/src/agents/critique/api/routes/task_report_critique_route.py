from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from src.agents.critique.graph.graph import task_report_critique_graph
from src.agents.critique.graph.schemas import TaskReportCritiqueResponse
from src.agents.critique.graph.state import TaskReportCritiqueState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/critique", tags=["critique"])


@router.post(
    "/analyse-task-report",
    response_model=TaskReportCritiqueResponse,
    summary="Critique an investigation task report document",
    description=(
        "Accept a .docx investigation task report, extract tasks and photographic evidence, "
        "run vision analysis on evidence photos, and critique each task, returning a flat list "
        "of actionable recommendations plus a strengths summary per task."
    ),
)
async def analyse_task_report(
    problem_statement: str,
    file: UploadFile = File(..., description="Investigation task report (.docx)"),
    event_type: str = "",
    task_description: str = "",
    deviation_id: Optional[int] = Form(
        None,
        description=(
            "Deviation this upload belongs to. Optional and unused today — once the backend "
            "starts sending it (together with task_index), DS can look up the previous attempt's "
            "accepted-but-still-unaddressed recommendations and check them against this report. "
            "See ds/src/agents/critique/GAPS.md."
        ),
    ),
    task_index: Optional[int] = Form(
        None,
        description="0-based task position within the RCI Plan this report is for. See deviation_id.",
    ),
) -> TaskReportCritiqueResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".docx":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .docx files are supported",
        )

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_path = Path(tmp.name)

        initial_state = TaskReportCritiqueState(
            file_path=str(temp_path),
            problem_statement=problem_statement,
            event_type=event_type,
            task_description=task_description,
            deviation_id=deviation_id,
            task_index=task_index,
        )
        final_state = await task_report_critique_graph.ainvoke(initial_state)

        result = final_state.get("final_result")
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Graph completed but produced no result",
            )
        return TaskReportCritiqueResponse(**result)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Task report critique failed for file: %s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process task report",
        )
    finally:
        await file.close()
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                logger.warning("Failed to clean up temp file: %s", temp_path)
