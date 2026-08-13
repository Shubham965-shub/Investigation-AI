"""
Deterministic aggregation: LLM checkpoint verdicts → scored sections → report.

Nothing here calls an LLM. Given the per-checkpoint verdicts, this module maps
each to marks via the rubric config and rolls them up into the API response.
A missing verdict is treated as the worst applicable outcome so an incomplete
model reply can never inflate a score.
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

from src.agents.scoring.api.schemas import (
    CheckpointScore,
    CheckpointVerdict,
    GroupScore,
    InfoRow,
    InfoTable,
    ScoringReportResponse,
    SectionScore,
)
from src.agents.scoring.rubric.rubric_config import (
    IQ_SECTIONS,
    TASK_REPORT_SECTION,
    Checkpoint,
    clamp_percentage,
    get_section,
    resolve_checkpoint,
)

_MISSING_NOTE = "No judgment returned by the scorer for this checkpoint; treated as not met."


def _default_verdict(cp: Checkpoint) -> str:
    return "none" if cp.kind == "classification" else "No"


def build_section_score(
    section: str, verdicts: Iterable[CheckpointVerdict]
) -> SectionScore:
    spec = get_section(section)
    verdict_map: Dict[str, CheckpointVerdict] = {v.id: v for v in verdicts}

    # Observability: the scorer is asked for exactly one verdict per checkpoint.
    # A shortfall means a section can score low purely because ids were omitted —
    # log it so that's distinguishable from a genuinely weak report.
    expected = {cp.id for cp in spec.checkpoints}
    missing = expected - set(verdict_map)
    unknown = set(verdict_map) - expected
    if missing:
        logger.warning("[%s] scorer omitted checkpoint ids %s → defaulting them to not-met.",
                       section, sorted(missing))
    if unknown:
        logger.warning("[%s] scorer returned unknown checkpoint ids %s → ignored.",
                       section, sorted(unknown))

    rows: List[CheckpointScore] = []
    marks_total = 0.0
    applicable_max = 0.0

    for cp in spec.checkpoints:
        v = verdict_map.get(cp.id)
        raw_verdict = v.verdict if v is not None else _default_verdict(cp)
        rationale = v.rationale if v is not None else _MISSING_NOTE
        evidence = v.evidence_quote if v is not None else ""

        norm_verdict, marks, applicable = resolve_checkpoint(cp, raw_verdict)
        marks_total += marks
        if applicable:
            applicable_max += cp.max_marks

        rows.append(
            CheckpointScore(
                id=cp.id,
                sub_criteria=cp.sub_criteria,
                checkpoint_text=cp.text,
                max_marks=cp.max_marks,
                verdict=norm_verdict,
                marks_awarded=marks,
                applicable=applicable,
                rationale=rationale,
                evidence_quote=evidence,
            )
        )

    percentage = clamp_percentage(marks_total / applicable_max * 100) if applicable_max > 0 else 0.0

    return SectionScore(
        section=spec.section,
        label=spec.label,
        marks_awarded=round(marks_total, 2),
        achievable_max=spec.achievable_max,
        applicable_max=round(applicable_max, 2),
        native_max=spec.native_max,
        percentage=percentage,
        checkpoints=rows,
    )


def _group_score(label: str, sections: List[SectionScore]) -> Optional[GroupScore]:
    if not sections:
        return None
    marks = sum(s.marks_awarded for s in sections)
    applicable = sum(s.applicable_max for s in sections)
    native = sum(s.native_max for s in sections)
    pct = clamp_percentage(marks / applicable * 100) if applicable > 0 else 0.0
    return GroupScore(
        label=label,
        marks_awarded=round(marks, 2),
        applicable_max=round(applicable, 2),
        native_max=native,
        percentage=pct,
    )


def build_score_info(section_scores: Dict[str, SectionScore]) -> List[InfoTable]:
    """Full per-section breakdown table — every checkpoint (not just the ones
    that lost marks), same shape as the marking-checklist spreadsheet. Built
    purely from data already in `section_scores` — no LLM call."""
    tables: List[InfoTable] = []
    for section in section_scores.values():
        rows = [
            InfoRow(
                id=cp.id,
                checkpoint=cp.checkpoint_text,
                max=cp.max_marks,
                verdict=cp.verdict,
                score=cp.marks_awarded,
                rationale=cp.rationale,
                evidence_quote=cp.evidence_quote,
            )
            for cp in section.checkpoints
        ]
        tables.append(
            InfoTable(
                section=section.section,
                label=section.label,
                native_max=section.native_max,
                marks_awarded=section.marks_awarded,
                percentage=section.percentage,
                rows=rows,
            )
        )
    return tables


def build_report_response(
    section_scores: Dict[str, SectionScore],
    *,
    event_type: Optional[str] = None,
) -> ScoringReportResponse:
    """Roll up per-section scores into the final response. `section_scores`
    contains only the sections that were detected and scored."""
    detected = [k for k in ("task_report", "rc", "impact", "capa") if k in section_scores]

    marks = sum(s.marks_awarded for s in section_scores.values())
    applicable = sum(s.applicable_max for s in section_scores.values())
    overall_pct = clamp_percentage(marks / applicable * 100) if applicable > 0 else 0.0

    task_group = _group_score(
        "Task Report Execution",
        [section_scores[TASK_REPORT_SECTION]] if TASK_REPORT_SECTION in section_scores else [],
    )
    iq_group = _group_score(
        "IQ Score",
        [section_scores[k] for k in IQ_SECTIONS if k in section_scores],
    )

    return ScoringReportResponse(
        score=int(round(overall_pct)),
        info=build_score_info(section_scores),
        event_type=event_type,
        detected_sections=detected,
        overall_percentage=overall_pct,
        overall_marks=round(marks, 2),
        overall_max=round(applicable, 2),
        task_report_execution=task_group,
        iq_score=iq_group,
        iq_score_percentage=iq_group.percentage if iq_group else None,
        sections=section_scores,
    )
