"""Shared shape for ds's /score/report `info` breakdown table (see
ds/src/agents/scoring/api/schemas.py's InfoTable/InfoRow) — used by both Task
Critique and RC & CAPA Critique's report schemas (2026-08-14, per the user:
shown via a small info icon next to each generated score)."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel


class ScoreBreakdownRow(BaseModel):
    id: str
    checkpoint: str
    max: float
    verdict: str
    score: float
    rationale: str
    evidence_quote: str = ""


class ScoreBreakdownTable(BaseModel):
    section: str  # task_report | rc | impact | capa
    label: str
    native_max: float
    marks_awarded: float
    percentage: float
    rows: List[ScoreBreakdownRow]