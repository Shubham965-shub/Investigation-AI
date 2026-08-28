"""
Regression tests for rci_plan's request validation, title/objective parsing,
and node-level normalization logic. There was zero test coverage for this
module before this file, despite a documented, previously-unfixed bug in the
shared TrackWise-field alias handling it depends on (Market Complaint's
"reported by" field — see rci_report/GAPS.md's 2026-08-07/2026-08-09 entries,
mirrored to a since-lost rci_plan/GAPS.md).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.agents.rci_plan.nodes import format_result, rephrase_rci_plan
from src.agents.rci_plan.routes import _split_title_and_objective
from src.agents.rci_plan.schemas import RciPlanRequest
from src.agents.rci_plan.state import RciPlanState


# ---------------------------------------------------------------------------
# RciPlanRequest / validate_trackwise_fields
# ---------------------------------------------------------------------------


def _valid_deviation_fields(**overrides):
    fields = {
        "title": "Batch weight deviation",
        "Batch Number / AR Number": "B12345",
        "Product / Material Code": "PM-001",
        "Product Name / Material Name": "Paracetamol 500mg",
        "Deviation To": "SOP-123",
        "Equipment Name": "Tablet Press",
        "description": "Weight out of spec",
        "Instrument ID Number": "INS-01",
        "Name of the Instrument": "Balance",
        "Observed By": "J. Doe",
        "Deviation Number": "DEV-001",
        "Date Opened": "2026-08-01",
        "Observation Date": "2026-08-01",
        "Observation Time": "10:00",
        "Failure Duration": "2h",
        "Related Market": "US",
        "Related Customer": "N/A",
        "Equipment ID": "EQ-01",
        "Equipment Number": "EN-01",
        "Deviation Owner": "QA Lead",
        "Originator": "J. Doe",
        "Impact on Deviation Batches": "None",
        "Immediate Cause Known": "No",
        "Cause Detail": "TBD",
    }
    fields.update(overrides)
    return fields


def test_rci_plan_request_accepts_fully_populated_deviation_fields():
    request = RciPlanRequest(event_type="Deviation", trackwise_fields=_valid_deviation_fields())
    assert request.trackwise_fields["observed_by"] == "J. Doe"


def test_rci_plan_request_rejects_missing_required_field():
    fields = _valid_deviation_fields()
    del fields["Observed By"]
    with pytest.raises(ValidationError, match="missing required fields"):
        RciPlanRequest(event_type="Deviation", trackwise_fields=fields)


def test_rci_plan_request_rejects_blank_required_field():
    with pytest.raises(ValidationError, match="empty fields"):
        RciPlanRequest(event_type="Deviation", trackwise_fields=_valid_deviation_fields(title="   "))


def test_rci_plan_request_rejects_unknown_event_type():
    with pytest.raises(ValidationError):
        RciPlanRequest(event_type="Unknown", trackwise_fields=_valid_deviation_fields())


def _valid_market_complaint_fields(**overrides):
    fields = {
        "title": "Discoloration complaint",
        "Date Complaint Received": "2026-08-01",
        "Reference Complaint Number": "RC-001",
        "description": "Customer reported tablet discoloration.",
        "Products Information": "Lamotrigine 200mg",
        "Dosage Form": "Tablet",
        "Market": "US",
        "Product Manufacturing Info": "Batch 7263940",
    }
    fields.update(overrides)
    return fields


def test_market_complaint_accepts_current_reported_by_alias():
    fields = _valid_market_complaint_fields(**{"Complaint Reported By": "Jane Doe"})
    request = RciPlanRequest(event_type="Market Complaint", trackwise_fields=fields)
    assert request.trackwise_fields["complaint_reported_by"] == "Jane Doe"


def test_market_complaint_accepts_legacy_reported_by_alias():
    """See rci_report/GAPS.md 2026-08-09: backend may still send the legacy
    'Market Complaint Reported By' key — both must normalize to the same
    output field, complaint_reported_by."""
    fields = _valid_market_complaint_fields(**{"Market Complaint Reported By": "Jane Doe"})
    request = RciPlanRequest(event_type="Market Complaint", trackwise_fields=fields)
    assert request.trackwise_fields["complaint_reported_by"] == "Jane Doe"


def test_market_complaint_missing_reported_by_under_either_key_is_rejected():
    fields = _valid_market_complaint_fields()
    with pytest.raises(ValidationError, match="missing required fields"):
        RciPlanRequest(event_type="Market Complaint", trackwise_fields=fields)


# ---------------------------------------------------------------------------
# _split_title_and_objective
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Real bug found while adding this test, not yet fixed: clean_title.rstrip(') ') "
        "(routes.py) strips ANY trailing ')'/space characters, not just a dangling remnant of "
        "the removed objective parenthetical — so when an earlier, legitimately-retained "
        "parenthetical group (e.g. '(FBD)') ends up at the new string's end, its own closing "
        "paren is eaten too. The function's own docstring worked example (this exact input) "
        "claims the title should come back as 'Drying Parameters (FBD)'; it actually comes back "
        "as 'Drying Parameters (FBD' — confirmed live, not a test authoring error."
    ),
)
def test_split_title_and_objective_extracts_last_parenthetical():
    title, objective = _split_title_and_objective(
        "Drying Parameters (FBD) (To examine why the moisture endpoint was missed)"
    )
    assert title == "Drying Parameters (FBD)"
    assert objective == "To examine why the moisture endpoint was missed"


def test_split_title_and_objective_strips_leading_objective_prefix():
    title, objective = _split_title_and_objective("Equipment Cleaning (Objective: verify swab results)")
    assert title == "Equipment Cleaning"
    assert objective == "verify swab results"


def test_split_title_and_objective_no_parens_returns_none_objective():
    title, objective = _split_title_and_objective("Root Cause Analysis")
    assert title == "Root Cause Analysis"
    assert objective is None


def test_split_title_and_objective_empty_parens_is_not_treated_as_a_parenthetical_at_all():
    """`\\(([^)]+)\\)` requires at least one character inside the parens, so a
    literal '()' is never matched as a group in the first place — the whole
    string (including the empty parens) is returned unchanged as the title,
    not stripped down to 'Section Title'."""
    title, objective = _split_title_and_objective("Section Title ()")
    assert title == "Section Title ()"
    assert objective is None


# ---------------------------------------------------------------------------
# nodes.py — format_result (pure aggregation, no I/O)
# ---------------------------------------------------------------------------


def _state(**overrides) -> RciPlanState:
    state = RciPlanState(event_type="Deviation", trackwise_fields={})
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


@pytest.mark.asyncio
async def test_format_result_prefers_rephrased_over_original():
    original = [{"title": "Original", "correlation": None, "tasks": [{"description": "a"}]}]
    rephrased = [{"title": "Rephrased", "correlation": None, "tasks": [{"description": "a"}, {"description": "b"}]}]
    state = _state(rci_plan_original=original, rci_plan_rephrased=rephrased, mapped_archetype={"id": 1, "name": "X"})

    result_state = await format_result(state)

    assert result_state.final_result["sections"] == rephrased
    assert result_state.final_result["total_sections_count"] == 1
    assert result_state.final_result["total_tasks_count"] == 2


@pytest.mark.asyncio
async def test_format_result_falls_back_to_original_when_rephrased_empty():
    original = [{"title": "Original", "correlation": None, "tasks": [{"description": "a"}]}]
    state = _state(rci_plan_original=original, rci_plan_rephrased=[], mapped_archetype={"id": 1, "name": "X"})

    result_state = await format_result(state)

    assert result_state.final_result["sections"] == original
    assert result_state.final_result["total_tasks_count"] == 1


@pytest.mark.asyncio
async def test_format_result_no_mapped_archetype_defaults_to_unknown():
    state = _state(rci_plan_original=[], rci_plan_rephrased=[], mapped_archetype=None, failure_type=None)

    result_state = await format_result(state)

    assert result_state.final_result["failure_type"] == "Unknown"
    assert result_state.final_result["archetype"]["id"] is None
    assert result_state.final_result["archetype"]["name"] == "Unknown"
    assert result_state.final_result["total_sections_count"] == 0
    assert result_state.final_result["total_tasks_count"] == 0


# ---------------------------------------------------------------------------
# nodes.py — rephrase_rci_plan task-shape normalization
# ---------------------------------------------------------------------------


def _mock_registry(prompt_text="prompt"):
    template = MagicMock()
    template.format.return_value = prompt_text
    registry = MagicMock()
    registry.get.return_value = template
    return registry


@pytest.mark.asyncio
async def test_rephrase_rci_plan_normalizes_mixed_task_shapes(monkeypatch):
    """The LLM may return tasks as dicts, bare strings, or other JSON types —
    all three must normalize to {"description": ...}."""
    state = _state(
        rci_plan_original=[{"title": "T1", "correlation": None, "tasks": [{"description": "d1"}]}],
    )

    llm = AsyncMock()
    llm.chat.return_value = '[{"title": "Section A", "tasks": [{"description": "Do X"}, "Do Y", 42]}]'

    monkeypatch.setattr("src.agents.rci_plan.nodes.get_llm_client", AsyncMock(return_value=llm))
    monkeypatch.setattr("src.agents.rci_plan.nodes.get_prompt_registry", lambda: _mock_registry())

    result_state = await rephrase_rci_plan(state)

    assert result_state.rci_plan_rephrased == [
        {
            "title": "Section A",
            "correlation": None,
            "tasks": [{"description": "Do X"}, {"description": "Do Y"}, {"description": "42"}],
        }
    ]


@pytest.mark.asyncio
async def test_rephrase_rci_plan_falls_back_to_original_on_invalid_json(monkeypatch):
    original = [{"title": "T1", "correlation": "Reason", "tasks": [{"description": "d1"}]}]
    state = _state(rci_plan_original=original)

    llm = AsyncMock()
    llm.chat.return_value = "not valid json"

    monkeypatch.setattr("src.agents.rci_plan.nodes.get_llm_client", AsyncMock(return_value=llm))
    monkeypatch.setattr("src.agents.rci_plan.nodes.get_prompt_registry", lambda: _mock_registry())

    result_state = await rephrase_rci_plan(state)

    assert result_state.rci_plan_rephrased == original


@pytest.mark.asyncio
async def test_rephrase_rci_plan_skips_llm_call_when_no_original_plan(monkeypatch):
    state = _state(rci_plan_original=[])
    get_llm = AsyncMock()
    monkeypatch.setattr("src.agents.rci_plan.nodes.get_llm_client", get_llm)

    result_state = await rephrase_rci_plan(state)

    assert result_state.rci_plan_rephrased == []
    get_llm.assert_not_called()
