"""
Regression tests for rci_plan's request validation, title/objective parsing,
and node-level normalization logic. There was zero test coverage for this
module before this file, despite a documented, previously-unfixed bug in the
shared TrackWise-field alias handling it depends on (Market Complaint's
"reported by" field — see rci_report/GAPS.md's 2026-08-07/2026-08-09 entries,
mirrored to a since-lost rci_plan/GAPS.md).
"""

import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.agents.app import create_app
from src.agents.rci_plan.nodes import format_result, rephrase_rci_plan
from src.agents.rci_plan.routes import _split_title_and_objective
from src.agents.rci_plan.schemas import RciPlanRequest
from src.agents.rci_plan.state import RciPlanState
from src.utils import deps


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


# ---------------------------------------------------------------------------
# Endpoint-level tests — POST /rci/plan, real graph, mocked LLM/DB
# ---------------------------------------------------------------------------


client = TestClient(create_app())


def _fake_connect(conn):
    async def connect(*args, **kwargs):
        return conn

    return connect


def _fake_conn(fetch_side_effect=None, fetchrow_side_effect=None):
    conn = MagicMock()
    if fetch_side_effect is not None:
        conn.fetch = AsyncMock(side_effect=fetch_side_effect)
    if fetchrow_side_effect is not None:
        conn.fetchrow = AsyncMock(side_effect=fetchrow_side_effect)
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


class _AsyncCM:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


@pytest.fixture(autouse=True)
def _reset_deps():
    yield
    deps._llm = None
    deps._pool = None
    deps._prompt_registry = None


def test_generate_rci_plan_high_confidence_returns_template_sections(monkeypatch):
    """UT-006-style scenario: a high-confidence archetype match (>= 0.7) takes
    fetch_rci_plan -> rephrase_rci_plan and returns the archetype's own
    (rephrased) template sections/tasks."""
    archetype_rows = [{"id": 8, "name": "Equipment Failure", "definition": "Cold chain excursion", "archetype_type_id": 1}]
    section_rows = [{"id": 30, "title": "Verify Equipment Logbook", "correlation": None, "six_m_bucket": "MACHINE"}]
    task_rows = [{"description": "Review the Cold Storage Unit 2 logbook"}]
    conn = _fake_conn(
        fetch_side_effect=[archetype_rows, section_rows, task_rows],
        fetchrow_side_effect=[{"id": 200}],  # plan_row lookup
    )
    monkeypatch.setattr("asyncpg.connect", _fake_connect(conn))

    registry, llm = _fake_registry_and_llm({
        "shared/map_to_archetype": '{"archetype_name": "Equipment Failure", "confidence_score": 0.9, "reasoning": "Matches equipment failure pattern."}',
        "rci_plan/rephrase_rci_plan": (
            '[{"title": "MACHINE: Verify Equipment Logbook", "correlation": null, '
            '"tasks": [{"description": "Review the Cold Storage Unit 2 logbook for the affected period."}]}]'
        ),
    })
    deps.set_llm(llm)
    deps.set_prompt_registry(registry)

    response = client.post(
        "/rci/plan",
        json={"event_type": "Deviation", "trackwise_fields": _valid_deviation_fields()},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["archetype"]["name"] == "Equipment Failure"
    assert data["total_sections_count"] == 1
    assert data["total_tasks_count"] == 1
    assert data["sections"][0]["title"] == "MACHINE: Verify Equipment Logbook"


def test_generate_rci_plan_low_confidence_returns_llm_inferred_plan(monkeypatch):
    """Low-confidence match (< 0.7) takes build_search_query ->
    fetch_historical_data -> infer_rci_plan_from_historical_data, drafting a
    plan directly from historical incidents rather than an existing template."""
    conn = _fake_conn(fetch_side_effect=[[]])  # no archetypes found
    monkeypatch.setattr("asyncpg.connect", _fake_connect(conn))
    monkeypatch.setattr(
        "src.agents.search_agent.graph.builder.build_search_graph",
        lambda **kwargs: _fake_search_graph(
            [{"title": "Similar cold storage excursion", "relevance_score": 0.55, "root_cause_summary": "Door seal failure"}]
        ),
    )

    registry, llm = _fake_registry_and_llm({
        "shared/map_to_archetype": '{"archetype_name": "Unclassified Cold Chain Event", "confidence_score": 0.2, "reasoning": "No confident archetype match found."}',
        "shared/build_search_query": "cold storage temperature excursion",
        "rci_plan/infer_rci_plan": (
            '[{"title": "Verify Cold Chain Controls", "correlation": null, '
            '"tasks": [{"description": "Inspect door seal integrity."}, {"description": "Review data logger calibration."}]}]'
        ),
    })
    deps.set_llm(llm)
    deps.set_prompt_registry(registry)
    deps.set_pool(MagicMock())

    response = client.post(
        "/rci/plan",
        json={"event_type": "Deviation", "trackwise_fields": _valid_deviation_fields()},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["archetype"]["name"] == "Unclassified Cold Chain Event"
    assert data["total_sections_count"] == 1
    assert data["total_tasks_count"] == 2


def test_generate_rci_plan_invalid_trackwise_fields_returns_422_without_touching_graph():
    response = client.post("/rci/plan", json={"event_type": "Deviation", "trackwise_fields": {}})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Endpoint-level tests — POST /rci/upload, real Excel ingestion path
# ---------------------------------------------------------------------------


def _build_rci_plan_workbook(sheet_name="Confirmed Assay Failure"):
    """Real .xlsx bytes matching the documented sheet layout: row 1 free-text
    label (ignored), row 2 header, row 3+ data — one section with two tasks,
    a single embedded-objective parenthetical (avoids the separately-tracked
    _split_title_and_objective multi-parenthetical bug)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append([f"{sheet_name} (Level 2)"])
    ws.append(["Sr.No.", "RCI PLAN", "Tasks", "Objective / Rationale"])
    ws.append([1, "Material Verification (Verify raw material COA)", "Check COA against specification", ""])
    ws.append([2, "Material Verification (Verify raw material COA)", "Verify vendor qualification status", ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_upload_rci_templates_rejects_unsupported_file_type():
    response = client.post(
        "/rci/upload",
        files={"file": ("plan.txt", b"not an excel file", "text/plain")},
    )
    assert response.status_code == 415
    assert "Excel" in response.json()["detail"]


def test_upload_rci_templates_ingests_real_workbook(monkeypatch):
    """UT-008/009/010-style scenario: a real .xlsx exercises the full
    ingestion path (archetype lookup/create, plan replace, section grouping
    with merged-cell ffill, per-row task insertion) end to end."""
    workbook_bytes = _build_rci_plan_workbook()

    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=[None, None])  # archetype_type miss, archetype miss
    conn.fetchval = AsyncMock(side_effect=[100, 55, 200, 300])  # type id, archetype id, plan id, section id
    conn.execute = AsyncMock(return_value="OK")
    conn.transaction = MagicMock(return_value=_AsyncCM(None))

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AsyncCM(conn))
    deps.set_pool(pool)

    response = client.post(
        "/rci/upload",
        files={
            "file": (
                "rci_templates.xlsx",
                workbook_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["archetypes_processed"] == ["Confirmed Assay Failure"]
    assert data["plans_created"] == 1
    assert data["sections_created"] == 1
    assert data["tasks_created"] == 2
