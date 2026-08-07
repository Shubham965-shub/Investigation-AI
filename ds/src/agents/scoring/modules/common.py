"""
Shared internals for the two scoring modules (task_report, iq).

Both modules judge each rubric checkpoint with an LLM and then map verdicts to
marks deterministically. To make the score reliable and reproducible, each
section is scored `_SAMPLES` times and the majority verdict per checkpoint is
taken (self-consistency) — LLM judging is not fully deterministic even at
temperature 0.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter, defaultdict
from typing import List

from src.agents.scoring.api.schemas import CheckpointVerdict, SectionScoringLLMOutput
from src.agents.scoring.rubric.rubric_config import get_section, resolve_checkpoint
from src.agents.scoring.support import SCORING_SYSTEM_PREAMBLE
from src.llm.client import LLMClient

logger = logging.getLogger(__name__)

# Self-consistency: samples per section. Tunable — higher = steadier, costlier.
_SAMPLES = 5


def render_checkpoints_block(section_keys: List[str]) -> str:
    """Render the rubric checkpoints for the given sections into the text block a
    scorer prompt lists. Keeps rubric_config as the single source of truth; the
    allowed verdicts (incl. classification tiers like RC / CAPA levels) come
    straight from the checkpoint definition."""
    lines: List[str] = []
    for section in section_keys:
        for cp in get_section(section).checkpoints:
            if cp.kind == "classification":
                verdicts = "/".join(cp.tiers or [])
            else:
                verdicts = "Yes/No/NA" if cp.allow_na else "Yes/No"
            na_flag = " (NA allowed)" if cp.allow_na else ""
            lines.append(f"- id {cp.id} [{verdicts}]{na_flag} — {cp.sub_criteria}: {cp.text}")
    return "\n".join(lines)


async def sample_section(llm: LLMClient, prompt: str) -> List[SectionScoringLLMOutput]:
    """Call the scorer _SAMPLES times concurrently at temperature 0; drop failures."""
    calls = [
        llm.get_structured_response(
            user_prompt=prompt,
            structure=SectionScoringLLMOutput,
            system_prompt=SCORING_SYSTEM_PREAMBLE,
            temperature=0,
        )
        for _ in range(_SAMPLES)
    ]
    results = await asyncio.gather(*calls, return_exceptions=True)
    good = [r for r in results if not isinstance(r, BaseException)]
    if not good:
        raise next(r for r in results if isinstance(r, BaseException))
    return good


def consensus(section: str, samples: List[SectionScoringLLMOutput]) -> List[CheckpointVerdict]:
    """Majority verdict per checkpoint across samples; ties break to the lowest
    marks (conservative). Verdicts are compared after rubric normalisation so
    'Assignable (proven)'/'assignable' and 'CAPA Level 3'/'level_3' each count as
    one vote."""
    cps = {cp.id: cp for cp in get_section(section).checkpoints}
    per_id: dict[str, list[CheckpointVerdict]] = defaultdict(list)
    for sample in samples:
        for v in sample.checkpoints:
            if v.id in cps:
                per_id[v.id].append(v)

    out: List[CheckpointVerdict] = []
    for cid, cp in cps.items():
        votes = per_id.get(cid)
        if not votes:
            continue  # missing everywhere → build_section_score defaults it to not-met
        norm = [(v, resolve_checkpoint(cp, v.verdict)[0]) for v in votes]
        counts = Counter(n for _, n in norm)
        top = max(counts.values())
        tied = [n for n, c in counts.items() if c == top]
        winner = tied[0] if len(tied) == 1 else min(tied, key=lambda n: resolve_checkpoint(cp, n)[1])
        rep = next(v for v, n in norm if n == winner)
        out.append(
            CheckpointVerdict(id=cid, verdict=winner, rationale=rep.rationale, evidence_quote=rep.evidence_quote)
        )
    return out
