"""Router-level tests for backend.routers.rci_plan — DB/DS-client layer entirely mocked, no live DB or network.

Per-route auth: generate/update_rci_plan use Depends(get_current_payload); export uses
Depends(get_current_username). get_rci_plan/get_open_investigators/update_rci_plan_prerequisites
declare no auth dependency of their own in this file's minimal test app — the blanket
Depends(get_current_username) they get in the real app is applied at app.include_router(...,
dependencies=[...]) time in backend/app.py, a cross-cutting concern out of scope here.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.auth import get_current_payload, get_current_username
from backend.routers.rci_plan import _NOT_FOUND_DETAIL, _add_working_days, router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_payload] = lambda: {"uid": 7, "username": "testuser", "roles": ["User"]}
    app.dependency_overrides[get_current_username] = lambda: "testuser"
    return TestClient(app)


@pytest.fixture
def client():
    return _make_client()


def _patch(monkeypatch, name, value):
    monkeypatch.setattr(f"backend.routers.rci_plan.{name}", value)


# ---------------------------------------------------------------------------
# POST /{record_id}/{rci_id}/generate
# ---------------------------------------------------------------------------


def _generate_ds_response():
    return {
        "event_type": "Deviation",
        "failure_type": "Equipment Failure",
        "archetype": {"id": 1, "name": "Equipment Failure", "is_new": False},
        "sections": [
            {"title": "Section A", "tasks": [{"description": "task 1"}]},
        ],
        "total_sections_count": 1,
        "total_tasks_count": 1,
    }


def test_generate_rci_plan_happy_path_sets_due_date_and_assignee(client, monkeypatch):
    _patch(monkeypatch, "fetch_problem_statement", AsyncMock(return_value=None))
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value={"investigator": "Jane Doe"}))
    ds_post = AsyncMock(return_value=_generate_ds_response())
    _patch(monkeypatch, "ds_post", ds_post)
    _patch(monkeypatch, "replace_rci_sections", AsyncMock())

    response = client.post(
        "/rci-plan/504544/none/generate",
        json={"event_type": "Deviation", "trackwise_fields": {"title": "Pump failure"}},
    )

    assert response.status_code == 200
    body = response.json()
    section = body["sections"][0]
    assert section["assignee"] == "Jane Doe"
    expected_due = _add_working_days(__import__("datetime").datetime.now(__import__("datetime").timezone.utc).date(), 5)
    assert section["due_date"] == expected_due.isoformat()


def test_generate_rci_plan_substitutes_generated_problem_statement_for_description(client, monkeypatch):
    _patch(monkeypatch, "fetch_problem_statement", AsyncMock(return_value="A generated problem statement."))
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=None))
    ds_post = AsyncMock(return_value=_generate_ds_response())
    _patch(monkeypatch, "ds_post", ds_post)
    _patch(monkeypatch, "replace_rci_sections", AsyncMock())

    response = client.post(
        "/rci-plan/504544/none/generate",
        json={"event_type": "Deviation", "trackwise_fields": {"title": "x", "description": "raw trackwise text"}},
    )

    assert response.status_code == 200
    sent_json = ds_post.call_args.kwargs["json"]
    assert sent_json["trackwise_fields"]["description"] == "A generated problem statement."


def test_generate_rci_plan_tolerates_non_numeric_record_id_for_problem_statement_lookup(client, monkeypatch):
    # fetch_problem_statement(int(record_id), ...) raises ValueError for a non-numeric id; caught, problem_statement stays None.
    _patch(monkeypatch, "fetch_problem_statement", AsyncMock(side_effect=AssertionError("should not be called with a bad id")))
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(side_effect=AssertionError("should not be called with a bad id")))
    ds_post = AsyncMock(return_value=_generate_ds_response())
    _patch(monkeypatch, "ds_post", ds_post)
    _patch(monkeypatch, "replace_rci_sections", AsyncMock())

    response = client.post(
        "/rci-plan/not-a-number/none/generate",
        json={"event_type": "Deviation", "trackwise_fields": {"title": "x"}},
    )
    assert response.status_code == 200


def test_generate_rci_plan_persistence_failure_does_not_break_response(client, monkeypatch):
    _patch(monkeypatch, "fetch_problem_statement", AsyncMock(return_value=None))
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=None))
    _patch(monkeypatch, "ds_post", AsyncMock(return_value=_generate_ds_response()))
    _patch(monkeypatch, "replace_rci_sections", AsyncMock(side_effect=RuntimeError("db down")))

    response = client.post(
        "/rci-plan/504544/none/generate",
        json={"event_type": "Deviation", "trackwise_fields": {"title": "x"}},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------


class _FakeUpstreamResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_upload_rci_templates_happy_path(client, monkeypatch):
    payload = {
        "status": "ok",
        "message": "done",
        "archetypes_processed": ["Equipment Failure"],
        "plans_created": 1,
        "sections_created": 2,
        "tasks_created": 3,
    }
    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=_FakeUpstreamResponse(payload))
    _patch(monkeypatch, "get_client", MagicMock(return_value=fake_client))

    response = client.post("/rci-plan/upload", files={"file": ("plans.xlsx", b"fake bytes", "application/octet-stream")})
    assert response.status_code == 200
    assert response.json() == payload


def test_upload_rci_templates_upstream_error_maps_to_http_exception(client, monkeypatch):
    import httpx

    request = httpx.Request("POST", "http://ds/rci/upload")
    response_obj = httpx.Response(422, json={"detail": "bad template"}, request=request)
    status_error = httpx.HTTPStatusError("error", request=request, response=response_obj)

    class _RaisingResponse:
        def raise_for_status(self):
            raise status_error

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=_RaisingResponse())
    _patch(monkeypatch, "get_client", MagicMock(return_value=fake_client))

    response = client.post("/rci-plan/upload", files={"file": ("plans.xlsx", b"fake bytes", "application/octet-stream")})
    assert response.status_code == 422
    assert response.json()["detail"] == "bad template"


# ---------------------------------------------------------------------------
# PUT /{record_id}/{rci_id}
# ---------------------------------------------------------------------------


def _section_payload(is_checked=True):
    return {
        "title": "Section A",
        "correlation": "high",
        "is_checked": is_checked,
        "tasks": [{"description": "task 1", "is_checked": True}],
    }


def test_update_rci_plan_rejects_non_numeric_record_id(client, monkeypatch):
    response = client.put("/rci-plan/not-a-number/none", json=[_section_payload()])
    assert response.status_code == 404
    assert response.json()["detail"] == _NOT_FOUND_DETAIL


def test_update_rci_plan_locked_when_task_critique_started(client, monkeypatch):
    _patch(monkeypatch, "any_task_critique_started", AsyncMock(return_value=True))
    replace_mock = AsyncMock()
    _patch(monkeypatch, "replace_rci_sections", replace_mock)

    response = client.put("/rci-plan/504544/none", json=[_section_payload()])
    assert response.status_code == 409
    replace_mock.assert_not_called()


def test_update_rci_plan_preserves_unchecked_sections_bugfix(client, monkeypatch):
    """Regression guard: is_checked must be threaded through to replace_rci_sections, not dropped
    (a prior bug silently reset every section back to checked on every save)."""
    _patch(monkeypatch, "any_task_critique_started", AsyncMock(return_value=False))
    replace_mock = AsyncMock()
    _patch(monkeypatch, "replace_rci_sections", replace_mock)

    response = client.put(
        "/rci-plan/504544/none",
        json=[_section_payload(is_checked=False), _section_payload(is_checked=True)],
    )
    assert response.status_code == 204
    sections_arg = replace_mock.call_args.args[1]
    assert sections_arg[0]["is_checked"] is False
    assert sections_arg[1]["is_checked"] is True


# ---------------------------------------------------------------------------
# GET /{record_id}/{rci_id}/export
# ---------------------------------------------------------------------------


def _investigation_row(qe_type="Deviation"):
    return {"qe_type": qe_type, "investigator": "Jane Doe", "rci_number": "RCI-1", "status": "RCI Plan"}


def test_export_rci_plan_rejects_non_numeric_record_id(client):
    response = client.get("/rci-plan/not-a-number/none/export")
    assert response.status_code == 404


def test_export_rci_plan_404s_when_investigation_not_found(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=None))
    response = client.get("/rci-plan/504544/none/export")
    assert response.status_code == 404


def test_export_rci_plan_404s_when_no_sections_persisted(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    _patch(monkeypatch, "fetch_rci_sections", AsyncMock(return_value=[]))
    response = client.get("/rci-plan/504544/none/export")
    assert response.status_code == 404


def test_export_rci_plan_happy_path_returns_docx_and_persists_snapshot(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    _patch(
        monkeypatch,
        "fetch_rci_sections",
        AsyncMock(return_value=[{"title": "Section A", "tasks": [{"description": "task 1"}]}]),
    )
    _patch(monkeypatch, "fetch_problem_statement", AsyncMock(return_value=None))
    checklist_dict = {
        "bench_top_verification_done": True,
        "preliminary_checklist_done": False,
        "personnel_interview_done": True,
        "photographic_evidence_collected": False,
    }
    _patch(monkeypatch, "fetch_rci_plan_prerequisites", AsyncMock(return_value=checklist_dict))
    build_docx_mock = MagicMock(return_value=(b"fake docx bytes", 0, 0))
    _patch(monkeypatch, "build_rci_plan_docx", build_docx_mock)
    _patch(monkeypatch, "fetch_user_by_username", AsyncMock(return_value={"id": 42}))
    insert_mock = AsyncMock()
    _patch(monkeypatch, "insert_rci_plan_export", insert_mock)

    response = client.get("/rci-plan/504544/none/export")

    assert response.status_code == 200
    assert response.content == b"fake docx bytes"
    assert "RCI_Plan_504544.docx" in response.headers["content-disposition"]
    passed_checklist = build_docx_mock.call_args.args[3]
    assert passed_checklist.bench_top_verification_done is True
    assert passed_checklist.preliminary_checklist_done is False
    insert_mock.assert_awaited_once()
    assert insert_mock.call_args.kwargs["approved_by"] == 42


def test_export_rci_plan_persist_failure_does_not_block_download(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    _patch(
        monkeypatch,
        "fetch_rci_sections",
        AsyncMock(return_value=[{"title": "Section A", "tasks": [{"description": "task 1"}]}]),
    )
    _patch(monkeypatch, "fetch_problem_statement", AsyncMock(return_value=None))
    _patch(
        monkeypatch,
        "fetch_rci_plan_prerequisites",
        AsyncMock(
            return_value={
                "bench_top_verification_done": False,
                "preliminary_checklist_done": False,
                "personnel_interview_done": False,
                "photographic_evidence_collected": False,
            }
        ),
    )
    _patch(monkeypatch, "build_rci_plan_docx", MagicMock(return_value=(b"fake docx bytes", 0, 0)))
    _patch(monkeypatch, "fetch_user_by_username", AsyncMock(side_effect=RuntimeError("db down")))
    _patch(monkeypatch, "insert_rci_plan_export", AsyncMock())

    response = client.get("/rci-plan/504544/none/export")
    assert response.status_code == 200
    assert response.content == b"fake docx bytes"


# ---------------------------------------------------------------------------
# GET /investigators
# ---------------------------------------------------------------------------


def test_get_open_investigators_passes_through(client, monkeypatch):
    _patch(monkeypatch, "fetch_open_investigators", AsyncMock(return_value=["Jane Doe", "John Smith"]))
    response = client.get("/rci-plan/investigators")
    assert response.status_code == 200
    assert response.json() == ["Jane Doe", "John Smith"]


# ---------------------------------------------------------------------------
# GET /{record_id}/{rci_id}
# ---------------------------------------------------------------------------


def test_get_rci_plan_rejects_non_numeric_record_id(client):
    response = client.get("/rci-plan/not-a-number/none")
    assert response.status_code == 404


def test_get_rci_plan_404s_when_investigation_not_found(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=None))
    response = client.get("/rci-plan/504544/none")
    assert response.status_code == 404


def test_get_rci_plan_happy_path_deviation_uses_extended_fields_and_prefills_problem_statement(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row("Deviation")))
    _patch(
        monkeypatch,
        "fetch_rci_sections",
        AsyncMock(return_value=[{"title": "Section A", "tasks": [{"description": "task 1"}]}]),
    )
    _patch(monkeypatch, "fetch_problem_statement", AsyncMock(return_value="Generated PS text"))
    _patch(
        monkeypatch,
        "fetch_rci_plan_prerequisites",
        AsyncMock(
            return_value={
                "bench_top_verification_done": False,
                "preliminary_checklist_done": False,
                "personnel_interview_done": False,
                "photographic_evidence_collected": False,
            }
        ),
    )
    _patch(monkeypatch, "any_task_critique_started", AsyncMock(return_value=True))

    response = client.get("/rci-plan/504544/none")
    assert response.status_code == 200
    body = response.json()
    assert body["event_type"] == "Deviation"
    assert body["trackwise_fields"]["description"] == "Generated PS text"
    assert body["locked_for_editing"] is True
    assert body["sections"][0]["title"] == "Section A"


def test_get_rci_plan_sections_none_when_nothing_persisted(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row("Out Of Specification")))
    _patch(monkeypatch, "fetch_rci_sections", AsyncMock(return_value=[]))
    _patch(monkeypatch, "fetch_problem_statement", AsyncMock(return_value=None))
    _patch(
        monkeypatch,
        "fetch_rci_plan_prerequisites",
        AsyncMock(
            return_value={
                "bench_top_verification_done": False,
                "preliminary_checklist_done": False,
                "personnel_interview_done": False,
                "photographic_evidence_collected": False,
            }
        ),
    )
    _patch(monkeypatch, "any_task_critique_started", AsyncMock(return_value=False))

    response = client.get("/rci-plan/504544/none")
    assert response.status_code == 200
    assert response.json()["sections"] is None
    assert response.json()["event_type"] == "OOS"


# ---------------------------------------------------------------------------
# PUT /{record_id}/{rci_id}/prerequisites
# ---------------------------------------------------------------------------


def test_update_rci_plan_prerequisites_rejects_non_numeric_record_id(client):
    response = client.put(
        "/rci-plan/not-a-number/none/prerequisites",
        json={
            "bench_top_verification_done": True,
            "preliminary_checklist_done": False,
            "personnel_interview_done": False,
            "photographic_evidence_collected": False,
        },
    )
    assert response.status_code == 404


def test_update_rci_plan_prerequisites_happy_path(client, monkeypatch):
    save_mock = AsyncMock()
    _patch(monkeypatch, "save_rci_plan_prerequisites", save_mock)

    response = client.put(
        "/rci-plan/504544/none/prerequisites",
        json={
            "bench_top_verification_done": True,
            "preliminary_checklist_done": True,
            "personnel_interview_done": False,
            "photographic_evidence_collected": False,
        },
    )
    assert response.status_code == 204
    save_mock.assert_awaited_once()
    assert save_mock.call_args.args[0] == 504544
    assert save_mock.call_args.args[1]["bench_top_verification_done"] is True
