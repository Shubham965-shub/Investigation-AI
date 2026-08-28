"""
Regression tests for evidence_collection's request validation, node-level
aggregation logic, and the archetype-confidence routing threshold. Zero
coverage before this file, and no GAPS.md exists yet for this module.
"""

import pytest
from pydantic import ValidationError

from src.agents.evidence_collection.graph import _route_after_archetype_mapping
from src.agents.evidence_collection.nodes import format_result
from src.agents.evidence_collection.schemas import EvidenceCollectionRequest
from src.agents.evidence_collection.state import EvidenceCollectionState


# ---------------------------------------------------------------------------
# EvidenceCollectionRequest / validate_trackwise_fields
# ---------------------------------------------------------------------------


def _valid_deviation_fields(**overrides):
    fields = {
        "title": "Temperature excursion",
        "Batch Number / AR Number": "AR-1001",
        "Product / Material Code": "PM-500",
        "Product Name / Material Name": "Paracetamol 500mg",
        "Deviation To": "Storage temperature exceeded",
        "Equipment Name": "Cold Storage Unit 2",
        "description": "Temperature excursion observed during storage.",
        "Instrument ID Number": "INS-77",
        "Name of the Instrument": "Data Logger",
        "Observed By": "Jane Doe",
    }
    fields.update(overrides)
    return fields


def test_evidence_collection_request_accepts_valid_deviation_fields():
    request = EvidenceCollectionRequest(event_type="Deviation", trackwise_fields=_valid_deviation_fields())
    assert request.trackwise_fields["batch_number_ar_number"] == "AR-1001"


def test_evidence_collection_request_rejects_missing_required_field():
    fields = _valid_deviation_fields()
    del fields["Observed By"]
    with pytest.raises(ValidationError, match="missing required fields"):
        EvidenceCollectionRequest(event_type="Deviation", trackwise_fields=fields)


def test_evidence_collection_request_rejects_blank_required_field():
    with pytest.raises(ValidationError, match="empty fields"):
        EvidenceCollectionRequest(event_type="Deviation", trackwise_fields=_valid_deviation_fields(description="  "))


def test_evidence_collection_request_rejects_unknown_event_type():
    with pytest.raises(ValidationError):
        EvidenceCollectionRequest(event_type="Not A Real Type", trackwise_fields=_valid_deviation_fields())


# ---------------------------------------------------------------------------
# graph.py — _route_after_archetype_mapping confidence threshold
# ---------------------------------------------------------------------------


def _state_with_confidence(score) -> EvidenceCollectionState:
    state = EvidenceCollectionState(event_type="Deviation", trackwise_fields={})
    state.confidence_score = score
    return state


def test_route_after_archetype_mapping_high_confidence_goes_to_fetch_evidence():
    assert _route_after_archetype_mapping(_state_with_confidence(0.8)) == "fetch_evidence"
    assert _route_after_archetype_mapping(_state_with_confidence(0.95)) == "fetch_evidence"


def test_route_after_archetype_mapping_low_confidence_goes_to_search_query():
    assert _route_after_archetype_mapping(_state_with_confidence(0.79)) == "build_search_query"
    assert _route_after_archetype_mapping(_state_with_confidence(0.0)) == "build_search_query"


def test_route_after_archetype_mapping_threshold_is_point_eight_not_point_seven():
    """The module's own docstring (graph.py:4-6) and routes.py both describe the
    split as '≥ 0.7' / '< 0.7', but the actual conditional branches at 0.8 —
    confirmed directly against the code, not the comment. A confidence of 0.75
    would take the HIGH-confidence path under the documented threshold but
    actually takes the LOW-confidence path. Pins the real behavior so a
    "docstring-matching" refactor doesn't silently change routing."""
    assert _route_after_archetype_mapping(_state_with_confidence(0.75)) == "build_search_query"


# ---------------------------------------------------------------------------
# nodes.py — format_result
# ---------------------------------------------------------------------------


def _ec_state(**overrides) -> EvidenceCollectionState:
    state = EvidenceCollectionState(event_type="Deviation", trackwise_fields={})
    state.mapped_archetype = {"id": 3, "name": "Equipment Failure"}
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


@pytest.mark.asyncio
async def test_format_result_prefers_rephrased_over_raw_evidence_list():
    state = _ec_state(
        evidence_list=[{"id": 1, "description": "Raw evidence"}],
        rephrased_evidence=[{"id": 1, "description": "Rephrased evidence", "is_new": False}],
        new_evidence=[],
    )
    result_state = await format_result(state)
    descriptions = [e["description"] for e in result_state.final_result["evidence"]]
    assert descriptions == ["Rephrased evidence"]


@pytest.mark.asyncio
async def test_format_result_falls_back_to_raw_evidence_list_when_not_rephrased():
    state = _ec_state(
        evidence_list=[{"id": 1, "description": "Raw evidence"}],
        rephrased_evidence=[],
        new_evidence=[],
    )
    result_state = await format_result(state)
    descriptions = [e["description"] for e in result_state.final_result["evidence"]]
    assert descriptions == ["Raw evidence"]


@pytest.mark.asyncio
async def test_format_result_appends_new_evidence_flagged_as_is_new():
    state = _ec_state(
        evidence_list=[{"id": 1, "description": "Existing evidence", "is_new": False}],
        rephrased_evidence=[],
        new_evidence=["A newly generated evidence item"],
    )
    result_state = await format_result(state)
    evidence = result_state.final_result["evidence"]
    assert evidence[-1] == {"description": "A newly generated evidence item", "is_new": True}
    assert result_state.final_result["total_evidence_count"] == 2


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Real bug, not yet fixed: format_result's `ev.get('description') or ev` falls back to "
        "embedding the WHOLE evidence dict as the description whenever description is falsy "
        "(e.g. rephrase_evidence produced an explicit empty string) — same pattern in "
        "interview_questionnaire/nodes.py. A blank rephrased description should surface as an "
        "empty string, not the dict itself."
    ),
)
@pytest.mark.asyncio
async def test_format_result_blank_description_stays_a_string_not_the_whole_dict():
    state = _ec_state(
        evidence_list=[{"id": 1, "description": "Existing evidence"}],
        rephrased_evidence=[{"id": 1, "description": "", "is_new": False}],
        new_evidence=[],
    )
    result_state = await format_result(state)
    assert result_state.final_result["evidence"][0]["description"] == ""
