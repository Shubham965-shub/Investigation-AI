"""
Tests for the adaptive self-consistency sampling in
src.agents.scoring.modules.common.sample_section.

Covers: unanimous cheap pass short-circuits at _MIN_SAMPLES; a disagreeing
cheap pass escalates to _MAX_SAMPLES; a failed call in the cheap pass also
escalates; consensus() over the resulting samples is unaffected.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agents.scoring.api.schemas import CheckpointVerdict, SectionScoringLLMOutput
from src.agents.scoring.modules import common
from src.agents.scoring.rubric.rubric_config import get_section

SECTION = "task_report"
CHECKPOINT_IDS = [cp.id for cp in get_section(SECTION).checkpoints]


def _output(verdict_for_first="Yes") -> SectionScoringLLMOutput:
    """One fake LLM sample: `verdict_for_first` on the first checkpoint id,
    'Yes' on every other checkpoint."""
    checkpoints = [
        CheckpointVerdict(
            id=cid,
            verdict=verdict_for_first if cid == CHECKPOINT_IDS[0] else "Yes",
            rationale="because",
            evidence_quote="",
        )
        for cid in CHECKPOINT_IDS
    ]
    return SectionScoringLLMOutput(checkpoints=checkpoints)


@pytest.fixture
def llm():
    return AsyncMock()


@pytest.mark.asyncio
async def test_unanimous_pass_stops_at_min_samples(llm):
    llm.get_structured_response.side_effect = [_output("Yes") for _ in range(common._MIN_SAMPLES)]

    samples = await common.sample_section(llm, "prompt", SECTION)

    assert llm.get_structured_response.call_count == common._MIN_SAMPLES
    assert len(samples) == common._MIN_SAMPLES


@pytest.mark.asyncio
async def test_disagreement_escalates_to_max_samples(llm):
    cheap_pass = [_output("Yes"), _output("Yes"), _output("No")]
    top_up = [_output("Yes"), _output("Yes")]
    llm.get_structured_response.side_effect = cheap_pass + top_up

    samples = await common.sample_section(llm, "prompt", SECTION)

    assert llm.get_structured_response.call_count == common._MAX_SAMPLES
    assert len(samples) == common._MAX_SAMPLES


@pytest.mark.asyncio
async def test_failed_call_in_cheap_pass_escalates(llm):
    llm.get_structured_response.side_effect = [
        RuntimeError("transient"),
        _output("Yes"),
        _output("Yes"),
        _output("Yes"),
        _output("Yes"),
    ]

    samples = await common.sample_section(llm, "prompt", SECTION)

    assert llm.get_structured_response.call_count == common._MAX_SAMPLES
    assert len(samples) == common._MAX_SAMPLES - 1  # one dropped failure


@pytest.mark.asyncio
async def test_all_calls_fail_raises(llm):
    llm.get_structured_response.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await common.sample_section(llm, "prompt", SECTION)

    assert llm.get_structured_response.call_count == common._MIN_SAMPLES


@pytest.mark.asyncio
async def test_consensus_over_escalated_samples_majority_wins(llm):
    cheap_pass = [_output("Yes"), _output("Yes"), _output("No")]
    top_up = [_output("No"), _output("No")]
    llm.get_structured_response.side_effect = cheap_pass + top_up

    samples = await common.sample_section(llm, "prompt", SECTION)
    verdicts = {v.id: v.verdict for v in common.consensus(SECTION, samples)}

    assert verdicts[CHECKPOINT_IDS[0]] == "No"  # 3-2 majority after escalation
