"""
Regression tests for interview_questionnaire's request validation,
node-level aggregation logic, and (below) full endpoint-level tests driving
the real graph through TestClient with the LLM/DB mocked at their actual
boundaries — zero coverage of any kind existed before this session, and no
GAPS.md exists yet for this module (see also shared/nodes.py's parse_input,
reused by every archetype-mapping workflow).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.agents.app import create_app
from src.agents.interview_questionnaire.nodes import format_result
from src.agents.interview_questionnaire.schemas import QuestionCollectionRequest
from src.agents.interview_questionnaire.state import InterviewQuestionCollectionState
from src.agents.shared.nodes import parse_input
from src.utils import deps


# ---------------------------------------------------------------------------
# QuestionCollectionRequest / validate_trackwise_fields
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


def test_question_collection_request_accepts_valid_deviation_fields():
    request = QuestionCollectionRequest(event_type="Deviation", trackwise_fields=_valid_deviation_fields())
    assert request.trackwise_fields["observed_by"] == "Jane Doe"


def test_question_collection_request_rejects_missing_required_field():
    fields = _valid_deviation_fields()
    del fields["Observed By"]
    with pytest.raises(ValidationError, match="missing required fields"):
        QuestionCollectionRequest(event_type="Deviation", trackwise_fields=fields)


def test_question_collection_request_rejects_blank_required_field():
    with pytest.raises(ValidationError, match="empty fields"):
        QuestionCollectionRequest(event_type="Deviation", trackwise_fields=_valid_deviation_fields(title="   "))


def test_question_collection_request_rejects_unknown_event_type():
    with pytest.raises(ValidationError):
        QuestionCollectionRequest(event_type="Not A Real Type", trackwise_fields=_valid_deviation_fields())


# ---------------------------------------------------------------------------
# shared/nodes.py — parse_input (reused by this and every other archetype workflow)
# ---------------------------------------------------------------------------


def _state(event_type, trackwise_fields, **overrides) -> InterviewQuestionCollectionState:
    state = InterviewQuestionCollectionState(event_type=event_type, trackwise_fields=trackwise_fields)
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


@pytest.mark.asyncio
async def test_parse_input_deviation_prefers_deviation_to_over_description():
    state = _state("Deviation", {"deviation_to": "Storage temp exceeded", "description": "fallback text"})
    result = await parse_input(state)
    assert result.failure_type == "Storage temp exceeded"


@pytest.mark.asyncio
async def test_parse_input_deviation_falls_back_to_description_when_deviation_to_blank():
    state = _state("Deviation", {"deviation_to": "", "description": "fallback text"})
    result = await parse_input(state)
    assert result.failure_type == "fallback text"


@pytest.mark.asyncio
async def test_parse_input_deviation_default_when_both_missing():
    state = _state("Deviation", {})
    result = await parse_input(state)
    assert result.failure_type == "Unknown Deviation"


@pytest.mark.asyncio
async def test_parse_input_oos_oot_prefers_failure_type_over_title():
    for event_type in ("OOS", "OOT", "OOS/OOT"):
        state = _state(event_type, {"failure_type": "Assay out of spec", "title": "fallback title"})
        result = await parse_input(state)
        assert result.failure_type == "Assay out of spec"


@pytest.mark.asyncio
async def test_parse_input_oos_default_when_both_missing():
    state = _state("OOS", {})
    result = await parse_input(state)
    assert result.failure_type == "Unknown OOS/OOT"


@pytest.mark.asyncio
async def test_parse_input_market_complaint_uses_title():
    state = _state("Market Complaint", {"title": "Tablet discoloration"})
    result = await parse_input(state)
    assert result.failure_type == "Tablet discoloration"


@pytest.mark.asyncio
async def test_parse_input_market_complaint_default_when_title_missing():
    state = _state("Market Complaint", {})
    result = await parse_input(state)
    assert result.failure_type == "Unknown Market Complaint"


@pytest.mark.asyncio
async def test_parse_input_unrecognized_event_type_yields_none():
    state = _state("Something Else", {"title": "x"})
    result = await parse_input(state)
    assert result.failure_type is None


# ---------------------------------------------------------------------------
# nodes.py — format_result
# ---------------------------------------------------------------------------


def _iq_state(**overrides) -> InterviewQuestionCollectionState:
    state = InterviewQuestionCollectionState(event_type="Deviation", trackwise_fields={})
    state.mapped_archetype = {"id": 3, "name": "Equipment Failure"}
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


@pytest.mark.asyncio
async def test_format_result_prefers_rephrased_over_raw_question_list():
    state = _iq_state(
        question_list=[{"id": 1, "description": "Raw question"}],
        rephrased_questions=[{"id": 1, "description": "Rephrased question", "is_new": False}],
        new_questions=[],
    )
    result_state = await format_result(state)
    descriptions = [q["description"] for q in result_state.final_result["questions"]]
    assert descriptions == ["Rephrased question"]


@pytest.mark.asyncio
async def test_format_result_falls_back_to_raw_question_list_when_not_rephrased():
    state = _iq_state(
        question_list=[{"id": 1, "description": "Raw question"}],
        rephrased_questions=[],
        new_questions=[],
    )
    result_state = await format_result(state)
    descriptions = [q["description"] for q in result_state.final_result["questions"]]
    assert descriptions == ["Raw question"]


@pytest.mark.asyncio
async def test_format_result_appends_new_questions_flagged_as_is_new():
    state = _iq_state(
        question_list=[{"id": 1, "description": "Existing question", "is_new": False}],
        rephrased_questions=[],
        new_questions=["A brand new question"],
    )
    result_state = await format_result(state)
    questions = result_state.final_result["questions"]
    assert questions[-1] == {"description": "A brand new question", "is_new": True}
    assert result_state.final_result["total_questions_count"] == 2


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Real bug, not yet fixed: format_result's `q.get('description') or q` falls back to "
        "embedding the WHOLE question dict as the description whenever description is falsy "
        "(e.g. rephrase_questions produced an explicit empty string) — same pattern in "
        "evidence_collection/nodes.py. A blank rephrased description should surface as an "
        "empty string, not the dict itself."
    ),
)
@pytest.mark.asyncio
async def test_format_result_blank_description_stays_a_string_not_the_whole_dict():
    state = _iq_state(
        question_list=[{"id": 1, "description": "Existing question"}],
        rephrased_questions=[{"id": 1, "description": "", "is_new": False}],
        new_questions=[],
    )
    result_state = await format_result(state)
    assert result_state.final_result["questions"][0]["description"] == ""


# ---------------------------------------------------------------------------
# Endpoint-level tests — POST /interview/questionnaire, real graph, mocked LLM/DB
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


def test_generate_questionnaire_high_confidence_returns_library_questions(monkeypatch):
    """UT-005-style scenario: a high-confidence archetype match (>= 0.7) takes
    fetch_questions -> rephrase_questions and returns the archetype's own
    (rephrased) question bank."""
    archetype_rows = [{"id": 7, "name": "Equipment Failure", "definition": "Cold chain excursion", "archetype_type_id": 1}]
    question_rows = [{"id": 20, "description": "What was the storage temperature at the time of excursion?"}]
    conn = _fake_conn(fetch_side_effect=[archetype_rows, question_rows])
    monkeypatch.setattr("asyncpg.connect", _fake_connect(conn))

    registry, llm = _fake_registry_and_llm({
        "shared/map_to_archetype": '{"archetype_name": "Equipment Failure", "confidence_score": 0.85, "reasoning": "Matches cold storage equipment failure pattern."}',
        "interview_questionnaire/rephrase_questions": (
            '[{"id": 20, "description": "What was the recorded temperature in Cold Storage Unit 2 during the excursion?"}]'
        ),
    })
    deps.set_llm(llm)
    deps.set_prompt_registry(registry)

    response = client.post(
        "/interview/questionnaire",
        json={"event_type": "Deviation", "trackwise_fields": _valid_deviation_fields()},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["archetype"]["name"] == "Equipment Failure"
    assert data["total_questions_count"] == 1
    assert data["questions"] == [
        {"description": "What was the recorded temperature in Cold Storage Unit 2 during the excursion?", "is_new": False}
    ]


def test_generate_questionnaire_low_confidence_returns_llm_inferred_questions(monkeypatch):
    """Low-confidence match (< 0.7) takes build_search_query ->
    fetch_historical_data -> infer_questions_from_historical_data, returning
    LLM-inferred questions flagged is_new: true."""
    conn = _fake_conn(fetch_side_effect=[[]])
    monkeypatch.setattr("asyncpg.connect", _fake_connect(conn))
    monkeypatch.setattr(
        "src.agents.search_agent.graph.builder.build_search_graph",
        lambda **kwargs: _fake_search_graph(
            [{"title": "Similar cold storage excursion", "relevance_score": 0.6, "root_cause_summary": "Door seal failure"}]
        ),
    )

    registry, llm = _fake_registry_and_llm({
        "shared/map_to_archetype": '{"archetype_name": "Unclassified Cold Chain Event", "confidence_score": 0.25, "reasoning": "No confident archetype match found."}',
        "shared/build_search_query": "cold storage temperature excursion",
        "interview_questionnaire/infer_questions": (
            '["Was the door seal inspected prior to the excursion?", '
            '"What is the calibration status of the temperature data logger?"]'
        ),
    })
    deps.set_llm(llm)
    deps.set_prompt_registry(registry)
    deps.set_pool(MagicMock())

    response = client.post(
        "/interview/questionnaire",
        json={"event_type": "Deviation", "trackwise_fields": _valid_deviation_fields()},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["archetype"]["name"] == "Unclassified Cold Chain Event"
    assert data["total_questions_count"] == 2
    assert all(item["is_new"] is True for item in data["questions"])


def test_generate_questionnaire_invalid_trackwise_fields_returns_422_without_touching_graph():
    response = client.post(
        "/interview/questionnaire",
        json={"event_type": "Deviation", "trackwise_fields": {}},
    )
    assert response.status_code == 422
