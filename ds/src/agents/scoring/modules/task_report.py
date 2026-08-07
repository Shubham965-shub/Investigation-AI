"""
Module 1 — Task Report scoring (Task Report Execution rubric, /40).

Scores the investigation-task-report section against its 12 checkpoints.
"""

from __future__ import annotations

from typing import Dict, Optional

from src.agents.scoring.api.schemas import SectionScore
from src.agents.scoring.modules.common import consensus, render_checkpoints_block, sample_section
from src.agents.scoring.rubric.aggregation import build_section_score
from src.llm.client import LLMClient
from src.prompt_registry.service import PromptRegistry

SECTION = "task_report"


async def score_task_report(
    text: str,
    problem_statement: str,
    event_type: Optional[str],
    llm: LLMClient,
    registry: PromptRegistry,
) -> Dict[str, SectionScore]:
    prompt = registry.get("scoring/score_task_report").format(
        event_type=event_type or "unspecified",
        problem_statement=problem_statement or "(not provided)",
        checkpoints=render_checkpoints_block([SECTION]),
        section_text=text,
    )
    samples = await sample_section(llm, prompt)
    return {SECTION: build_section_score(SECTION, consensus(SECTION, samples))}
