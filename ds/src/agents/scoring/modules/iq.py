"""
Module 2 — IQ scoring: Root Cause (/30), Impact (/10), CAPA (/20).

Each of the three sections is scored INDEPENDENTLY from its own section text only
(no cross-section context) — per the requirement to "score everything based on the
specific section only". The three run concurrently; a failure in one does not
discard the others.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from src.agents.scoring.api.schemas import SectionScore
from src.agents.scoring.modules.common import consensus, render_checkpoints_block, sample_section
from src.agents.scoring.rubric.aggregation import build_section_score
from src.agents.scoring.rubric.rubric_config import IQ_SECTIONS
from src.llm.client import LLMClient
from src.prompt_registry.service import PromptRegistry

logger = logging.getLogger(__name__)

_PROMPT = {
    "rc": "scoring/score_rc",
    "impact": "scoring/score_impact",
    "capa": "scoring/score_capa",
}


async def _score_one(
    section: str,
    text: str,
    problem_statement: str,
    event_type: Optional[str],
    llm: LLMClient,
    registry: PromptRegistry,
) -> tuple[str, SectionScore]:
    prompt = registry.get(_PROMPT[section]).format(
        event_type=event_type or "unspecified",
        problem_statement=problem_statement or "(not provided)",
        checkpoints=render_checkpoints_block([section]),
        section_text=text,
    )
    samples = await sample_section(llm, prompt, section)
    return section, build_section_score(section, consensus(section, samples))


async def score_iq(
    sections: Dict[str, str],
    problem_statement: str,
    event_type: Optional[str],
    llm: LLMClient,
    registry: PromptRegistry,
) -> Dict[str, SectionScore]:
    """Score whichever of RC / Impact / CAPA are present, each from its own text."""
    present = [k for k in IQ_SECTIONS if k in sections]
    results = await asyncio.gather(
        *[_score_one(k, sections[k], problem_statement, event_type, llm, registry) for k in present],
        return_exceptions=True,
    )
    out: Dict[str, SectionScore] = {}
    for r in results:
        if isinstance(r, BaseException):
            logger.error("IQ section scorer failed: %s", r, exc_info=r)
            continue
        section, score = r
        out[section] = score
    return out
