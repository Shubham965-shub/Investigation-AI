"""Pydantic request / response models for the report-scoring API."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# ── LLM structured-output models (internal) ────────────────────────────────────


class CheckpointVerdict(BaseModel):
    """One judgment the LLM returns per rubric checkpoint. No marks — the LLM
    never computes scores; it only judges."""

    id: str = Field(..., description="Rubric checkpoint id, e.g. '3.1a' or '1'")
    verdict: str = Field(
        ...,
        description="Binary checkpoints: 'Yes' | 'No' | 'NA'. "
        "RC checkpoint '1': 'assignable' | 'probable' | 'none'.",
    )
    rationale: str = Field(..., description="Why this verdict — specific to the report content.")
    evidence_quote: str = Field(
        "",
        description="Verbatim span from the section supporting a 'Yes'/tier; "
        "for 'No'/'NA' state what is missing or why inapplicable.",
    )


class SectionScoringLLMOutput(BaseModel):
    """What each scorer (Task Report scorer, IQ scorer) returns."""

    checkpoints: List[CheckpointVerdict]


class SectionDetectionLLMOutput(BaseModel):
    """Section splitter output. Any section absent from the document is returned
    as an empty string."""

    event_type: Optional[str] = Field(
        None, description="Deviation | OOS | OOT | Market Complaint, if determinable."
    )
    problem_statement: str = ""
    task_report_text: str = ""
    rc_text: str = ""
    impact_text: str = ""
    capa_text: str = ""


# ── API response models ────────────────────────────────────────────────────────


class CheckpointScore(BaseModel):
    id: str
    sub_criteria: str
    checkpoint_text: str
    max_marks: float
    verdict: str                 # normalised: Yes | No | NA | assignable | probable | none
    marks_awarded: float
    applicable: bool             # False when NA (excluded from denominator)
    rationale: str
    evidence_quote: str = ""


class SectionScore(BaseModel):
    section: str                 # task_report | rc | impact | capa
    label: str
    marks_awarded: float
    achievable_max: float        # sum of checkpoint maxima (max earnable)
    applicable_max: float        # achievable_max minus NA checkpoints
    native_max: float            # total as printed on the source checklist
    percentage: float            # marks_awarded / applicable_max, clamped [0,100]
    checkpoints: List[CheckpointScore]


class GroupScore(BaseModel):
    label: str
    marks_awarded: float
    applicable_max: float
    native_max: float
    percentage: float


class ScoringReportResponse(BaseModel):
    # Headline integer score for the FE (rounded overall percentage, 0–100).
    score: int
    event_type: Optional[str] = None
    detected_sections: List[str]
    # Full-precision percentage (float) behind `score`:
    overall_percentage: float
    overall_marks: float
    overall_max: float
    # Native checklist roll-ups (present only when their sections were scored):
    task_report_execution: Optional[GroupScore] = None   # /40
    iq_score: Optional[GroupScore] = None                 # /60 (RC + Impact + CAPA)
    iq_score_percentage: Optional[float] = None
    # Full per-section detail (the "why"), kept for the backend / audit:
    sections: Dict[str, SectionScore]


# ── Per-section (JSON, no file) request ────────────────────────────────────────


class SectionScoreRequest(BaseModel):
    """Score a single already-extracted section's text against its rubric."""

    section: str = Field(..., description="task_report | rc | impact | capa")
    text: str = Field(..., description="The section text to score.")
    event_type: Optional[str] = None
    problem_statement: Optional[str] = None
    # Optional cross-section context so linkage checkpoints can be verified even
    # when scoring a single section (e.g. RC text when scoring CAPA).
    rc_text: Optional[str] = None
    impact_text: Optional[str] = None
    capa_text: Optional[str] = None
