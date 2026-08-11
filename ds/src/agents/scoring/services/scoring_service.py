"""
Scoring orchestrator.

Ties the two scoring modules together for a whole report:
  1. detect + split the document into its sections
  2. score the present sections concurrently — Module 1 (Task Report) and
     Module 2 (RC / Impact / CAPA, each scored from its own section only)
  3. aggregate deterministically into the API response

All marks/percentages are computed in `rubric.aggregation`; the modules only
obtain per-checkpoint verdicts (majority-voted) from the LLM.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from src.agents.scoring.api.schemas import (
    ScoringReportResponse,
    SectionScore,
    SectionScoreRequest,
)
from src.agents.scoring.modules.iq import score_iq
from src.agents.scoring.modules.task_report import score_task_report
from src.agents.scoring.rubric.aggregation import build_report_response
from src.agents.scoring.rubric.rubric_config import IQ_SECTIONS
from src.agents.scoring.services.section_detection import detect_and_split, present_sections
from src.utils.deps import get_llm_client, get_prompt_registry

logger = logging.getLogger(__name__)


async def score_report(
    file_path: Path,
    *,
    event_type_override: Optional[str] = None,
) -> ScoringReportResponse:
    """Detect the report's sections and score every one that is present."""
    llm = await get_llm_client()
    registry = get_prompt_registry()

    detection = await detect_and_split(file_path, llm, registry)
    event_type = event_type_override or detection.event_type
    present = present_sections(detection)

    if not present:
        logger.warning("score_report: no scoreable sections detected in %s", file_path)
        return build_report_response({}, event_type=event_type)

    coros = []
    if "task_report" in present:
        coros.append(
            score_task_report(present["task_report"], detection.problem_statement, event_type, llm, registry)
        )
    iq_texts = {k: present[k] for k in IQ_SECTIONS if k in present}
    if iq_texts:
        coros.append(score_iq(iq_texts, detection.problem_statement, event_type, llm, registry))

    # Resilient: a failure in one module must not discard the other's results.
    section_scores: Dict[str, SectionScore] = {}
    failures: List[BaseException] = []
    for result in await asyncio.gather(*coros, return_exceptions=True):
        if isinstance(result, BaseException):
            logger.error("A scoring module failed: %s", result, exc_info=result)
            failures.append(result)
        else:
            section_scores.update(result)

    # Sections were detected but none could be scored → surface the error rather
    # than a misleading empty report.
    if present and not section_scores:
        raise failures[0] if failures else RuntimeError("All section scorers failed")

    return build_report_response(section_scores, event_type=event_type)


async def score_report_from_bytes(
    data: bytes,
    filename: str,
    *,
    event_type_override: Optional[str] = None,
) -> ScoringReportResponse:
    """Score a report supplied as raw bytes (the production 'pull doc from DB'
    entry point): the bytes are written to a temp file whose extension is taken
    from `filename` (so .docx / .pdf handling works) and scored, then removed."""
    suffix = Path(filename).suffix.lower() or ".docx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.close()
        return await score_report(Path(tmp.name), event_type_override=event_type_override)
    finally:
        try:
            Path(tmp.name).unlink()
        except OSError:
            logger.warning("Failed to clean up temp file: %s", tmp.name)


async def score_single_section(req: SectionScoreRequest) -> SectionScore:
    """Score one already-extracted section's text (JSON endpoint). Scored from
    its own text only, consistent with the two modules."""
    llm = await get_llm_client()
    registry = get_prompt_registry()

    if req.section == "task_report":
        result = await score_task_report(
            req.text, req.problem_statement or "", req.event_type, llm, registry
        )
        return result["task_report"]

    if req.section in IQ_SECTIONS:
        result = await score_iq(
            {req.section: req.text}, req.problem_statement or "", req.event_type, llm, registry
        )
        if req.section not in result:
            raise RuntimeError(f"Scoring failed for section {req.section!r}")
        return result[req.section]

    raise ValueError(f"Unknown section: {req.section!r}")
