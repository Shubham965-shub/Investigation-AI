"""Router-level tests for backend/routers/problem_statement.py — DB queries and the DS HTTP
client are mocked (monkeypatched where imported into the router module); no live DB/DS service."""
from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from backend.routers import problem_statement as ps_router
from backend.routers.auth import get_current_payload


def _make_client():
    app = FastAPI()
    app.include_router(ps_router.router)
    app.dependency_overrides[get_current_payload] = lambda: {"uid": 7, "username": "tester"}
    return TestClient(app)


def _investigation_row(**overrides):
    row = {
        "qe_type": "Deviation",
        "status": "RCI Plan",
        "description": "Pump seal failure",
        "title": "Pump issue",
        "criticality": "Major",
        "event_classification": "Major",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# POST /{record_id}/{rci_id}/generate
# ---------------------------------------------------------------------------


def test_generate_problem_statement_happy_path(monkeypatch):
    monkeypatch.setattr(
        ps_router, "ds_post", AsyncMock(return_value={"event_type": "Deviation", "problem_statement": "Generated text"})
    )
    save_mock = AsyncMock()
    monkeypatch.setattr(ps_router, "save_problem_statement", save_mock)

    client = _make_client()
    response = client.post(
        "/problem-statement/504544/none/generate",
        json={"event_type": "Deviation", "trackwise_fields": {"title": "t"}},
    )

    assert response.status_code == 200
    assert response.json() == {"event_type": "Deviation", "problem_statement": "Generated text"}
    save_mock.assert_awaited_once()
    args, kwargs = save_mock.call_args
    assert args[0] == 504544  # deviation_id parsed from record_id
    assert kwargs["rci_id"] is None  # "none" segment normalized to real NULL
    assert kwargs["generated_by"] == 7


def test_generate_problem_statement_survives_persistence_failure(monkeypatch):
    monkeypatch.setattr(
        ps_router, "ds_post", AsyncMock(return_value={"event_type": "Deviation", "problem_statement": "Generated text"})
    )
    monkeypatch.setattr(ps_router, "save_problem_statement", AsyncMock(side_effect=RuntimeError("db down")))

    client = _make_client()
    response = client.post(
        "/problem-statement/504544/504545/generate",
        json={"event_type": "Deviation", "trackwise_fields": {}},
    )

    assert response.status_code == 200
    assert response.json()["problem_statement"] == "Generated text"


# ---------------------------------------------------------------------------
# GET /{record_id}/{rci_id}
# ---------------------------------------------------------------------------


def test_get_problem_statement_404_for_non_integer_record_id():
    client = _make_client()
    response = client.get("/problem-statement/not-a-number/none")
    assert response.status_code == 404


def test_get_problem_statement_404_when_row_not_found(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=None))
    client = _make_client()
    response = client.get("/problem-statement/504544/none")
    assert response.status_code == 404


def test_get_problem_statement_404_when_qe_type_unresolved(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row(qe_type="Unknown Type")))
    client = _make_client()
    response = client.get("/problem-statement/504544/none")
    assert response.status_code == 404


def test_get_problem_statement_happy_path_deviation_not_extended(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(ps_router, "fetch_problem_statement", AsyncMock(return_value="Existing statement"))
    monkeypatch.setattr(ps_router, "fetch_evidence_items", AsyncMock(return_value=[]))
    monkeypatch.setattr(ps_router, "fetch_problem_statement_enhancements", AsyncMock(return_value=None))

    client = _make_client()
    response = client.get("/problem-statement/504544/none")

    assert response.status_code == 200
    body = response.json()
    assert body["event_type"] == "Deviation"
    assert body["problem_statement"] == "Existing statement"
    assert body["locked_for_editing"] is False
    assert body["criticality"] == "Major"
    # Deviation isn't extended, so an extended-only field must not appear.
    assert "Deviation Number" not in body["trackwise_fields"]


def test_get_problem_statement_market_complaint_is_extended(monkeypatch):
    row = _investigation_row(qe_type="Complaint", complaint_number="C-1", title="MC title")
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=row))
    monkeypatch.setattr(ps_router, "fetch_problem_statement", AsyncMock(return_value=None))
    monkeypatch.setattr(ps_router, "fetch_evidence_items", AsyncMock(return_value=[]))
    monkeypatch.setattr(ps_router, "fetch_problem_statement_enhancements", AsyncMock(return_value=None))

    client = _make_client()
    response = client.get("/problem-statement/504544/none")

    assert response.status_code == 200
    body = response.json()
    assert body["event_type"] == "Market Complaint"
    assert body["trackwise_fields"]["Complaint Number"] == "C-1"


def test_get_problem_statement_locked_when_evidence_already_collected(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(ps_router, "fetch_problem_statement", AsyncMock(return_value="Existing"))
    monkeypatch.setattr(ps_router, "fetch_evidence_items", AsyncMock(return_value=[{"description": "item"}]))
    monkeypatch.setattr(ps_router, "fetch_problem_statement_enhancements", AsyncMock(return_value=None))

    client = _make_client()
    response = client.get("/problem-statement/504544/none")

    assert response.json()["locked_for_editing"] is True


# ---------------------------------------------------------------------------
# POST /{record_id}/{rci_id}/enhancements/generate
# ---------------------------------------------------------------------------


def test_generate_enhancements_404_for_non_integer_record_id():
    client = _make_client()
    response = client.post("/problem-statement/abc/none/enhancements/generate")
    assert response.status_code == 404


def test_generate_enhancements_404_when_no_problem_statement_exists(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_problem_statement", AsyncMock(return_value=None))
    client = _make_client()
    response = client.post("/problem-statement/504544/none/enhancements/generate")
    assert response.status_code == 404


def test_generate_enhancements_happy_path(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_problem_statement", AsyncMock(return_value="Existing statement"))
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row(description="Raw text")))
    monkeypatch.setattr(
        ps_router,
        "ds_post",
        AsyncMock(return_value={"enhancements": [{"category": "Detail", "tw_excerpt": "raw", "llm_excerpt": "polished"}]}),
    )
    save_mock = AsyncMock()
    monkeypatch.setattr(ps_router, "save_problem_statement_enhancements", save_mock)

    client = _make_client()
    response = client.post("/problem-statement/504544/none/enhancements/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["enhancements"] == [{"category": "Detail", "tw_excerpt": "raw", "llm_excerpt": "polished"}]
    save_mock.assert_awaited_once()


def test_generate_enhancements_survives_persistence_failure(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_problem_statement", AsyncMock(return_value="Existing statement"))
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(ps_router, "ds_post", AsyncMock(return_value={"enhancements": []}))
    monkeypatch.setattr(ps_router, "save_problem_statement_enhancements", AsyncMock(side_effect=RuntimeError("db down")))

    client = _make_client()
    response = client.post("/problem-statement/504544/none/enhancements/generate")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# PUT /{record_id}/{rci_id}
# ---------------------------------------------------------------------------


def test_update_problem_statement_404_for_non_integer_record_id():
    client = _make_client()
    response = client.put("/problem-statement/abc/none", json={"problem_statement": "edited"})
    assert response.status_code == 404


def test_update_problem_statement_404_when_row_not_found(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=None))
    client = _make_client()
    response = client.put("/problem-statement/504544/none", json={"problem_statement": "edited"})
    assert response.status_code == 404


def test_update_problem_statement_404_when_qe_type_unresolved(monkeypatch):
    monkeypatch.setattr(
        ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row(qe_type="Unknown Type"))
    )
    client = _make_client()
    response = client.put("/problem-statement/504544/none", json={"problem_statement": "edited"})
    assert response.status_code == 404


def test_update_problem_statement_409_when_evidence_already_started(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(ps_router, "fetch_evidence_items", AsyncMock(return_value=[{"description": "item"}]))

    client = _make_client()
    response = client.put("/problem-statement/504544/none", json={"problem_statement": "edited"})

    assert response.status_code == 409


def test_update_problem_statement_happy_path(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(ps_router, "fetch_evidence_items", AsyncMock(return_value=[]))
    save_mock = AsyncMock()
    monkeypatch.setattr(ps_router, "save_problem_statement", save_mock)
    delete_mock = AsyncMock()
    monkeypatch.setattr(ps_router, "delete_problem_statement_enhancements", delete_mock)

    client = _make_client()
    response = client.put("/problem-statement/504544/none", json={"problem_statement": "edited text"})

    assert response.status_code == 200
    body = response.json()
    assert body["problem_statement"] == "edited text"
    assert body["locked_for_editing"] is False
    save_mock.assert_awaited_once()
    delete_mock.assert_awaited_once()


def test_update_problem_statement_survives_enhancement_cleanup_failure(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(ps_router, "fetch_evidence_items", AsyncMock(return_value=[]))
    monkeypatch.setattr(ps_router, "save_problem_statement", AsyncMock())
    monkeypatch.setattr(ps_router, "delete_problem_statement_enhancements", AsyncMock(side_effect=RuntimeError("db down")))

    client = _make_client()
    response = client.put("/problem-statement/504544/none", json={"problem_statement": "edited text"})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /{record_id}/{rci_id}/historic
# ---------------------------------------------------------------------------


def test_historic_returns_empty_list_for_non_integer_record_id():
    client = _make_client()
    response = client.get("/problem-statement/abc/none/historic")
    assert response.status_code == 200
    assert response.json() == []


def test_historic_returns_empty_list_when_row_not_found(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=None))
    client = _make_client()
    response = client.get("/problem-statement/504544/none/historic")
    assert response.json() == []


def test_historic_returns_empty_list_when_no_query_text(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row(description=None, title=None)))
    monkeypatch.setattr(ps_router, "fetch_problem_statement", AsyncMock(return_value=None))
    client = _make_client()
    response = client.get("/problem-statement/504544/none/historic")
    assert response.json() == []


def test_historic_returns_empty_list_when_search_raises(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(ps_router, "fetch_problem_statement", AsyncMock(return_value="Existing statement"))
    monkeypatch.setattr(
        ps_router,
        "ds_post",
        AsyncMock(side_effect=HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="unreachable")),
    )
    client = _make_client()
    response = client.get("/problem-statement/504544/none/historic")
    assert response.status_code == 200
    assert response.json() == []


def test_historic_returns_empty_list_when_no_candidates_survive_filtering(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(ps_router, "fetch_problem_statement", AsyncMock(return_value="Existing statement"))
    monkeypatch.setattr(
        ps_router,
        "ds_post",
        AsyncMock(return_value={"ranked_results": [{"deviation_id": 504544, "title": "Self only"}]}),
    )
    client = _make_client()
    response = client.get("/problem-statement/504544/none/historic")
    assert response.json() == []


def test_historic_happy_path_excludes_current_record_and_resolves_statuses(monkeypatch):
    monkeypatch.setattr(ps_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(ps_router, "fetch_problem_statement", AsyncMock(return_value="Existing statement"))
    monkeypatch.setattr(
        ps_router,
        "ds_post",
        AsyncMock(
            return_value={
                "ranked_results": [
                    {"deviation_id": 504544, "title": "Self — must be excluded", "relevance_score": 0.99},
                    {"deviation_id": 111111, "title": "Similar case", "relevance_score": 0.8765},
                    {"deviation_id": 222222, "relevance_score": 0.5},
                ]
            }
        ),
    )
    monkeypatch.setattr(ps_router, "fetch_investigation_statuses", AsyncMock(return_value={111111: "Open", 222222: "Closed"}))

    client = _make_client()
    response = client.get("/problem-statement/504544/none/historic")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0] == {"deviation_id": 111111, "title": "Similar case", "status": "Open", "relevance_score": 0.8765}
    assert body[1]["title"] == "Untitled"  # missing title defaults
    assert body[1]["status"] == "Closed"
