"""Router-level tests for backend/routers/questionnaire.py — DB queries and the DS HTTP client
are mocked (monkeypatched where imported into the router module); no live DB/DS service."""
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import questionnaire as questionnaire_router
from backend.routers.auth import get_current_payload


def _make_client():
    app = FastAPI()
    app.include_router(questionnaire_router.router)
    app.dependency_overrides[get_current_payload] = lambda: {"uid": 7, "username": "tester"}
    return TestClient(app)


def _investigation_row(**overrides):
    row = {"qe_type": "Deviation", "status": "Interview Questionnaire", "description": "desc", "title": "title"}
    row.update(overrides)
    return row


_ARCHETYPE = {"id": 1, "name": "Pump Seal Failure", "is_new": False, "confidence_score": 0.9, "reasoning": "match"}


# ---------------------------------------------------------------------------
# POST /{record_id}/{rci_id}/generate
# ---------------------------------------------------------------------------


def test_generate_questionnaire_happy_path(monkeypatch):
    monkeypatch.setattr(
        questionnaire_router,
        "ds_post",
        AsyncMock(
            return_value={
                "event_type": "Deviation",
                "failure_type": "Equipment",
                "archetype": _ARCHETYPE,
                "questions": [{"description": "Who observed the deviation?", "is_new": False, "is_checked": True}],
                "total_questions_count": 1,
            }
        ),
    )
    replace_mock = AsyncMock()
    monkeypatch.setattr(questionnaire_router, "replace_questionnaire_items", replace_mock)

    client = _make_client()
    response = client.post(
        "/questionnaire/504544/none/generate",
        json={"event_type": "Deviation", "trackwise_fields": {"title": "t"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_questions_count"] == 1
    replace_mock.assert_awaited_once()
    args, kwargs = replace_mock.call_args
    assert args[0] == 504544
    assert args[1] == [{"description": "Who observed the deviation?", "is_checked": True}]
    assert kwargs["rci_id"] is None
    assert kwargs["generated_by"] == 7


def test_generate_questionnaire_survives_persistence_failure(monkeypatch):
    monkeypatch.setattr(
        questionnaire_router,
        "ds_post",
        AsyncMock(
            return_value={
                "event_type": "Deviation",
                "failure_type": "Equipment",
                "archetype": _ARCHETYPE,
                "questions": [],
                "total_questions_count": 0,
            }
        ),
    )
    monkeypatch.setattr(questionnaire_router, "replace_questionnaire_items", AsyncMock(side_effect=RuntimeError("db down")))

    client = _make_client()
    response = client.post(
        "/questionnaire/504544/none/generate",
        json={"event_type": "Deviation", "trackwise_fields": {}},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /{record_id}/{rci_id}
# ---------------------------------------------------------------------------


def test_get_questionnaire_404_for_non_integer_record_id():
    client = _make_client()
    response = client.get("/questionnaire/not-a-number/none")
    assert response.status_code == 404


def test_get_questionnaire_404_when_row_not_found(monkeypatch):
    monkeypatch.setattr(questionnaire_router, "fetch_investigation_row", AsyncMock(return_value=None))
    client = _make_client()
    response = client.get("/questionnaire/504544/none")
    assert response.status_code == 404


def test_get_questionnaire_404_when_qe_type_unresolved(monkeypatch):
    monkeypatch.setattr(
        questionnaire_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row(qe_type="Unknown"))
    )
    client = _make_client()
    response = client.get("/questionnaire/504544/none")
    assert response.status_code == 404


def test_get_questionnaire_returns_none_when_nothing_persisted_yet(monkeypatch):
    monkeypatch.setattr(questionnaire_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(questionnaire_router, "fetch_questionnaire_items", AsyncMock(return_value=[]))
    client = _make_client()
    response = client.get("/questionnaire/504544/none")
    assert response.status_code == 200
    assert response.json()["questions"] is None


def test_get_questionnaire_returns_persisted_items(monkeypatch):
    monkeypatch.setattr(questionnaire_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(
        questionnaire_router,
        "fetch_questionnaire_items",
        AsyncMock(return_value=[{"description": "Who observed it?", "is_new": False, "is_checked": True}]),
    )
    client = _make_client()
    response = client.get("/questionnaire/504544/none")
    assert response.status_code == 200
    body = response.json()
    assert body["questions"] == [{"description": "Who observed it?", "is_new": False, "is_checked": True}]


# ---------------------------------------------------------------------------
# PUT /{record_id}/{rci_id}
# ---------------------------------------------------------------------------


def test_update_questionnaire_404_for_non_integer_record_id():
    client = _make_client()
    response = client.put("/questionnaire/not-a-number/none", json=[])
    assert response.status_code == 404


def test_update_questionnaire_happy_path_replaces_items(monkeypatch):
    replace_mock = AsyncMock()
    monkeypatch.setattr(questionnaire_router, "replace_questionnaire_items", replace_mock)

    client = _make_client()
    response = client.put(
        "/questionnaire/504544/none",
        json=[
            {"description": "Who observed it?", "is_new": False, "is_checked": True},
            {"description": "New question", "is_new": True, "is_checked": False},
        ],
    )

    assert response.status_code == 204
    replace_mock.assert_awaited_once()
    args, kwargs = replace_mock.call_args
    assert args[0] == 504544
    assert args[1] == [
        {"description": "Who observed it?", "is_checked": True},
        {"description": "New question", "is_checked": False},
    ]
    assert kwargs["rci_id"] is None
    assert kwargs["generated_by"] == 7
