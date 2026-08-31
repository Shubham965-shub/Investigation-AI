"""
Regression tests for evidence_collection's request validation, node-level
aggregation logic, the archetype-confidence routing threshold, and (below)
full endpoint-level tests driving the real graph through TestClient with the
LLM/DB mocked at their actual boundaries (asyncpg.connect, get_llm_client,
get_prompt_registry, and search_agent's build_search_graph for the
low-confidence path) — no coverage of any kind existed for this module
before this session, and no GAPS.md exists yet either.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.agents.app import create_app
from src.agents.evidence_collection.graph import _route_after_archetype_mapping
from src.agents.evidence_collection.nodes import format_result
from src.agents.evidence_collection.schemas import EvidenceCollectionRequest
from src.agents.evidence_collection.state import EvidenceCollectionState
from src.utils import deps


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


# ---------------------------------------------------------------------------
# Endpoint-level tests — POST /evidence/collect, real graph, mocked LLM/DB
#
# fetch_archetypes/fetch_evidence bypass deps entirely and call
# asyncpg.connect(settings.DATABASE_URL) directly (see nodes.py/shared/nodes.py
# comments on the DB_PASSWORD percent-encoding gotcha) — both modules `import
# asyncpg`, so patching the asyncpg.connect attribute once covers every call
# site. map_to_archetype/rephrase_evidence/build_search_query/
# infer_evidence_from_historical_data all go through deps.get_llm_client() +
# deps.get_prompt_registry(), and the low-confidence path additionally routes
# through search_agent's build_search_graph(...).ainvoke(...).
# ---------------------------------------------------------------------------


client = TestClient(create_app())


def _fake_connect(conn):
    async def connect(*args, **kwargs):
        return conn

    return connect


def _fake_conn(fetch_side_effect):
    conn = MagicMock()
    conn.fetch = AsyncMock(side_effect=fetch_side_effect)
    conn.close = AsyncMock()
    return conn


def _fake_registry_and_llm(chat_responses):
    """chat_responses maps a prompt-registry key to the string llm.chat(...)
    should return when called with that key's (fake) formatted prompt."""

    class _Template:
        def __init__(self, name):
            self._name = name

        def format(self, **kwargs):
            return f"PROMPT::{self._name}"

    registry = MagicMock()
    registry.get.side_effect = lambda name: _Template(name)

    async def fake_chat(prompt, *args, **kwargs):
        name = prompt.split("PROMPT::", 1)[1]
        return chat_responses[name]

    llm = AsyncMock()
    llm.chat = AsyncMock(side_effect=fake_chat)
    return registry, llm


def _fake_search_graph(final_results):
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={"final_results": final_results})
    return graph


@pytest.fixture(autouse=True)
def _reset_deps():
    yield
    deps._llm = None
    deps._pool = None
    deps._prompt_registry = None


def test_collect_evidence_high_confidence_returns_library_evidence(monkeypatch):
    """UT-003-style scenario: a high-confidence archetype match (>= 0.8) takes
    the fetch_evidence -> rephrase_evidence path and returns the archetype's
    own (rephrased) evidence library, not LLM-inferred items."""
    archetype_rows = [{"id": 5, "name": "Equipment Failure", "definition": "Cold chain excursion", "archetype_type_id": 1}]
    evidence_rows = [{"id": 10, "description": "Check equipment logbook"}]
    conn = _fake_conn(fetch_side_effect=[archetype_rows, evidence_rows])
    monkeypatch.setattr("asyncpg.connect", _fake_connect(conn))

    registry, llm = _fake_registry_and_llm({
        "shared/map_to_archetype": '{"archetype_name": "Equipment Failure", "confidence_score": 0.9, "reasoning": "Matches cold storage equipment failure pattern."}',
        "evidence_collection/rephrase_evidence": '[{"id": 10, "description": "Review Cold Storage Unit 2 equipment logbook for the affected period."}]',
    })
    deps.set_llm(llm)
    deps.set_prompt_registry(registry)

    response = client.post(
        "/evidence/collect",
        json={"event_type": "Deviation", "trackwise_fields": _valid_deviation_fields()},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["archetype"]["name"] == "Equipment Failure"
    assert data["archetype"]["confidence_score"] == 0.9
    assert data["total_evidence_count"] == 1
    assert data["evidence"] == [
        {"description": "Review Cold Storage Unit 2 equipment logbook for the affected period.", "is_new": False}
    ]


def test_collect_evidence_low_confidence_returns_llm_inferred_evidence(monkeypatch):
    """UT-004-style scenario: a low-confidence match (< 0.8) takes the
    build_search_query -> fetch_historical_data -> infer_evidence path and
    returns LLM-inferred evidence, each flagged is_new: true."""
    conn = _fake_conn(fetch_side_effect=[[]])  # no archetypes found at all
    monkeypatch.setattr("asyncpg.connect", _fake_connect(conn))
    monkeypatch.setattr(
        "src.agents.search_agent.graph.builder.build_search_graph",
        lambda **kwargs: _fake_search_graph(
            [{"title": "Similar cold storage excursion", "relevance_score": 0.7, "root_cause_summary": "Door seal failure"}]
        ),
    )

    registry, llm = _fake_registry_and_llm({
        "shared/map_to_archetype": '{"archetype_name": "Unclassified Cold Chain Event", "confidence_score": 0.3, "reasoning": "No confident archetype match found."}',
        "shared/build_search_query": "cold storage temperature excursion",
        "evidence_collection/infer_evidence": (
            '["Verify cold storage temperature logs for the past 30 days.", '
            '"Check calibration records for the temperature data logger."]'
        ),
    })
    deps.set_llm(llm)
    deps.set_prompt_registry(registry)
    deps.set_pool(MagicMock())

    response = client.post(
        "/evidence/collect",
        json={"event_type": "Deviation", "trackwise_fields": _valid_deviation_fields()},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["archetype"]["name"] == "Unclassified Cold Chain Event"
    assert data["archetype"]["confidence_score"] == 0.3
    assert data["total_evidence_count"] == 2
    assert all(item["is_new"] is True for item in data["evidence"])
    assert "Verify cold storage temperature logs for the past 30 days." in [
        item["description"] for item in data["evidence"]
    ]


def test_collect_evidence_invalid_trackwise_fields_returns_422_without_touching_graph():
    """Schema validation fails before the graph (and therefore any LLM/DB
    call) ever runs — no mocking needed for this path."""
    response = client.post(
        "/evidence/collect",
        json={"event_type": "Deviation", "trackwise_fields": {}},
    )
    assert response.status_code == 422
