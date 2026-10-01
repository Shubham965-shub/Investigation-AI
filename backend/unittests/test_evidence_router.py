"""Router-level tests for backend/routers/evidence.py — DB queries and the DS HTTP client are
mocked (monkeypatched where imported into the router module); no live DB/DS service."""
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import evidence as evidence_router
from backend.routers.auth import get_current_payload


def _make_client():
    app = FastAPI()
    app.include_router(evidence_router.router)
    app.dependency_overrides[get_current_payload] = lambda: {"uid": 7, "username": "tester"}
    return TestClient(app)


def _investigation_row(**overrides):
    row = {"qe_type": "Deviation", "status": "Evidence Collection", "description": "desc", "title": "title"}
    row.update(overrides)
    return row


_ARCHETYPE = {"id": 1, "name": "Pump Seal Failure", "is_new": False, "confidence_score": 0.9, "reasoning": "match"}


# ---------------------------------------------------------------------------
# POST /{record_id}/{rci_id}/collect
# ---------------------------------------------------------------------------


def test_collect_evidence_happy_path(monkeypatch):
    monkeypatch.setattr(
        evidence_router,
        "ds_post",
        AsyncMock(
            return_value={
                "event_type": "Deviation",
                "failure_type": "Equipment",
                "archetype": _ARCHETYPE,
                "evidence": [{"description": "Check pump seal", "is_new": False, "is_checked": True}],
                "total_evidence_count": 1,
            }
        ),
    )
    replace_mock = AsyncMock()
    monkeypatch.setattr(evidence_router, "replace_evidence_items", replace_mock)

    client = _make_client()
    response = client.post(
        "/evidence/504544/none/collect",
        json={"event_type": "Deviation", "trackwise_fields": {"title": "t"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_evidence_count"] == 1
    assert body["evidence"][0]["description"] == "Check pump seal"
    replace_mock.assert_awaited_once()
    args, kwargs = replace_mock.call_args
    assert args[0] == 504544
    assert args[1] == [{"description": "Check pump seal", "is_checked": True}]
    assert kwargs["rci_id"] is None
    assert kwargs["generated_by"] == 7


def test_collect_evidence_survives_persistence_failure(monkeypatch):
    monkeypatch.setattr(
        evidence_router,
        "ds_post",
        AsyncMock(
            return_value={
                "event_type": "Deviation",
                "failure_type": "Equipment",
                "archetype": _ARCHETYPE,
                "evidence": [],
                "total_evidence_count": 0,
            }
        ),
    )
    monkeypatch.setattr(evidence_router, "replace_evidence_items", AsyncMock(side_effect=RuntimeError("db down")))

    client = _make_client()
    response = client.post(
        "/evidence/504544/none/collect",
        json={"event_type": "Deviation", "trackwise_fields": {}},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /{record_id}/{rci_id}
# ---------------------------------------------------------------------------


def test_get_evidence_404_for_non_integer_record_id():
    client = _make_client()
    response = client.get("/evidence/not-a-number/none")
    assert response.status_code == 404


def test_get_evidence_404_when_row_not_found(monkeypatch):
    monkeypatch.setattr(evidence_router, "fetch_investigation_row", AsyncMock(return_value=None))
    client = _make_client()
    response = client.get("/evidence/504544/none")
    assert response.status_code == 404


def test_get_evidence_404_when_qe_type_unresolved(monkeypatch):
    monkeypatch.setattr(evidence_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row(qe_type="Unknown")))
    client = _make_client()
    response = client.get("/evidence/504544/none")
    assert response.status_code == 404


def test_get_evidence_returns_none_when_nothing_persisted_yet(monkeypatch):
    monkeypatch.setattr(evidence_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(evidence_router, "fetch_evidence_items", AsyncMock(return_value=[]))
    client = _make_client()
    response = client.get("/evidence/504544/none")
    assert response.status_code == 200
    assert response.json()["evidence"] is None


def test_get_evidence_returns_persisted_items(monkeypatch):
    monkeypatch.setattr(evidence_router, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    monkeypatch.setattr(
        evidence_router,
        "fetch_evidence_items",
        AsyncMock(return_value=[{"description": "Check seal", "is_new": False, "is_checked": True}]),
    )
    client = _make_client()
    response = client.get("/evidence/504544/none")
    assert response.status_code == 200
    body = response.json()
    assert body["evidence"] == [{"description": "Check seal", "is_new": False, "is_checked": True}]


# ---------------------------------------------------------------------------
# PUT /{record_id}/{rci_id}
# ---------------------------------------------------------------------------


def test_update_evidence_404_for_non_integer_record_id():
    client = _make_client()
    response = client.put("/evidence/not-a-number/none", json=[])
    assert response.status_code == 404


def test_update_evidence_happy_path_replaces_items(monkeypatch):
    replace_mock = AsyncMock()
    monkeypatch.setattr(evidence_router, "replace_evidence_items", replace_mock)

    client = _make_client()
    response = client.put(
        "/evidence/504544/none",
        json=[
            {"description": "Check seal", "is_new": False, "is_checked": True},
            {"description": "New item", "is_new": True, "is_checked": False},
        ],
    )

    assert response.status_code == 204
    replace_mock.assert_awaited_once()
    args, kwargs = replace_mock.call_args
    assert args[0] == 504544
    assert args[1] == [
        {"description": "Check seal", "is_checked": True, "is_new": False},
        {"description": "New item", "is_checked": False, "is_new": True},
    ]
    assert kwargs["rci_id"] is None
    assert kwargs["generated_by"] == 7
