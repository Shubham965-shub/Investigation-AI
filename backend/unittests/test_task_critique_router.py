"""
Router-level tests for backend/routers/task_critique.py — no live DB, no live DS service.
Each test module builds a minimal FastAPI app that mounts only this router, with the DB
query functions / DS client / docx-parsing helpers monkeypatched where they're imported
INTO the router module (not where they're defined), and the auth dependency overridden
directly on the app.
"""
import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import task_critique as module
from backend.routers.auth import get_current_payload


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_payload] = lambda: {"uid": 7, "username": "tester", "roles": ["User"]}
    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


def _row(**overrides):
    row = {
        "qe_type": "Deviation",
        "description": "A real description",
        "title": "A real title",
        "investigator": "Jane Doe",
        "due_date": None,
    }
    row.update(overrides)
    return row


def _section(**overrides):
    section = {"title": "Investigate seal failure", "correlation": "high", "tasks": ["Check seal", "Check pump"], "due_date": "01/02/2026", "assignee": "Jane Doe"}
    section.update(overrides)
    return section


def _report(**overrides):
    report = {
        "id": 1,
        "attempt_number": 1,
        "file_name": "report.docx",
        "is_gospel": False,
        "summary": None,
        "task_score": None,
        "score_breakdown": [],
        "critique_failed": False,
        "critique_pending": False,
        "uploaded_at": datetime.datetime(2026, 1, 1, 12, 0),
        "recommendations": [],
    }
    report.update(overrides)
    return report


# ---------------------------------------------------------------------------
# GET /{record_id}/{rci_id}
# ---------------------------------------------------------------------------


def test_get_task_critique_404_for_non_numeric_record_id(client):
    response = client.get("/task-critique/not-a-number/none")
    assert response.status_code == 404
    assert response.json()["detail"] == module._NOT_FOUND_DETAIL


def test_get_task_critique_404_when_investigation_not_found(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=None))
    response = client.get("/task-critique/504544/none")
    assert response.status_code == 404
    assert response.json()["detail"] == module._NOT_FOUND_DETAIL


def test_get_task_critique_404_when_event_type_unresolvable(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row(qe_type="Something Unknown")))
    response = client.get("/task-critique/504544/none")
    assert response.status_code == 404


def test_get_task_critique_no_source_document(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "fetch_source_document", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "fetch_latest_rci_plan_export_docx", AsyncMock(return_value=None))
    response = client.get("/task-critique/504544/none")
    assert response.status_code == 200
    body = response.json()
    assert body["has_source_document"] is False
    assert body["sections"] == []


def test_get_task_critique_falls_back_to_rci_plan_export_when_no_manual_upload(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "fetch_source_document", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "fetch_latest_rci_plan_export_docx", AsyncMock(return_value=b"docxbytes"))
    monkeypatch.setattr(module, "extract_task_sections", lambda b: [_section()])
    monkeypatch.setattr(module, "fetch_reports_by_task_index", AsyncMock(return_value={}))
    response = client.get("/task-critique/504544/none")
    assert response.status_code == 200
    body = response.json()
    assert body["has_source_document"] is True
    assert body["source_document_name"] == "RCI_Plan_504544.docx"
    assert len(body["sections"]) == 1
    section = body["sections"][0]
    assert section["title"] == "Investigate seal failure"
    assert section["task_count"] == 2
    assert section["status"] == "pending"
    assert section["can_upload"] is True
    assert section["locked"] is False


def test_get_task_critique_prefers_manual_upload_over_rci_plan_export(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "fetch_source_document", AsyncMock(return_value=(b"manual", "manual.docx")))
    fetch_export = AsyncMock(return_value=b"should-not-be-used")
    monkeypatch.setattr(module, "fetch_latest_rci_plan_export_docx", fetch_export)
    monkeypatch.setattr(module, "extract_task_sections", lambda b: [_section()])
    monkeypatch.setattr(module, "fetch_reports_by_task_index", AsyncMock(return_value={}))
    response = client.get("/task-critique/504544/none")
    assert response.status_code == 200
    assert response.json()["source_document_name"] == "manual.docx"
    fetch_export.assert_not_called()


def test_get_task_critique_section_shows_processing_status(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "fetch_source_document", AsyncMock(return_value=(b"manual", "manual.docx")))
    monkeypatch.setattr(module, "extract_task_sections", lambda b: [_section()])
    pending_report = _report(critique_pending=True)
    monkeypatch.setattr(module, "fetch_reports_by_task_index", AsyncMock(return_value={0: pending_report}))
    response = client.get("/task-critique/504544/none")
    section = response.json()["sections"][0]
    assert section["status"] == "processing"
    assert section["can_upload"] is False
    assert section["locked"] is False


# ---------------------------------------------------------------------------
# POST /{record_id}/{rci_id}/source-document
# ---------------------------------------------------------------------------


def test_upload_source_document_rejects_unparseable_file(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))

    def _raise(_bytes):
        raise ValueError("bad docx")

    monkeypatch.setattr(module, "extract_task_sections", _raise)
    response = client.post("/task-critique/504544/none/source-document", files={"file": ("bad.docx", b"junk", "application/octet-stream")})
    assert response.status_code == 400
    assert "Could not read" in response.json()["detail"]


def test_upload_source_document_rejects_when_no_tasks_found(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "extract_task_sections", lambda b: [])
    response = client.post("/task-critique/504544/none/source-document", files={"file": ("empty.docx", b"junk", "application/octet-stream")})
    assert response.status_code == 400
    assert "No tasks" in response.json()["detail"]


def test_upload_source_document_success_persists_and_returns_list(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "extract_task_sections", lambda b: [_section()])
    upsert = AsyncMock()
    monkeypatch.setattr(module, "upsert_source_document", upsert)
    monkeypatch.setattr(module, "fetch_source_document", AsyncMock(return_value=(b"manual", "manual.docx")))
    monkeypatch.setattr(module, "fetch_reports_by_task_index", AsyncMock(return_value={}))
    response = client.post("/task-critique/504544/none/source-document", files={"file": ("manual.docx", b"content", "application/octet-stream")})
    assert response.status_code == 200
    assert response.json()["has_source_document"] is True
    upsert.assert_awaited_once()
    args, kwargs = upsert.await_args
    assert args[0] == 504544
    assert args[1] == "manual.docx"


# ---------------------------------------------------------------------------
# POST /{record_id}/{rci_id}/sections/{task_index}/upload
# ---------------------------------------------------------------------------


def _mock_upload_chain(monkeypatch, *, section=None, report=None, missing_markers=None):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "fetch_source_document", AsyncMock(return_value=(b"manual", "manual.docx")))
    monkeypatch.setattr(module, "extract_task_sections", lambda b: [section or _section()])
    monkeypatch.setattr(module, "fetch_reports_by_task_index", AsyncMock(return_value={0: report} if report else {}))
    monkeypatch.setattr(module, "missing_task_report_markers", lambda b: missing_markers or [])
    monkeypatch.setattr(module, "fetch_problem_statement", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "_process_task_report_async", AsyncMock())


def test_upload_task_report_404_when_no_source_document(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "fetch_source_document", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "fetch_latest_rci_plan_export_docx", AsyncMock(return_value=None))
    response = client.post("/task-critique/504544/none/sections/0/upload", files={"file": ("r.docx", b"x", "application/octet-stream")})
    assert response.status_code == 404


def test_upload_task_report_404_when_task_index_unknown(client, monkeypatch):
    _mock_upload_chain(monkeypatch)
    response = client.post("/task-critique/504544/none/sections/99/upload", files={"file": ("r.docx", b"x", "application/octet-stream")})
    assert response.status_code == 404
    assert response.json()["detail"] == module._TASK_NOT_FOUND_DETAIL


def test_upload_task_report_409_when_locked(client, monkeypatch):
    # 3rd attempt already used -> locked, regardless of decisions.
    locked_report = _report(attempt_number=3, recommendations=[])
    _mock_upload_chain(monkeypatch, report=locked_report)
    response = client.post("/task-critique/504544/none/sections/0/upload", files={"file": ("r.docx", b"x", "application/octet-stream")})
    assert response.status_code == 409


def test_upload_task_report_400_when_markers_missing(client, monkeypatch):
    upsert = AsyncMock()
    _mock_upload_chain(monkeypatch, missing_markers=["problem statement", "findings"])
    monkeypatch.setattr(module, "upsert_report", upsert)
    response = client.post("/task-critique/504544/none/sections/0/upload", files={"file": ("r.docx", b"x", "application/octet-stream")})
    assert response.status_code == 400
    upsert.assert_not_called()


def test_upload_task_report_success_persists_as_processing(client, monkeypatch):
    _mock_upload_chain(monkeypatch)
    upsert = AsyncMock(return_value=42)
    monkeypatch.setattr(module, "upsert_report", upsert)
    response = client.post("/task-critique/504544/none/sections/0/upload", files={"file": ("r.docx", b"x", "application/octet-stream")})
    assert response.status_code == 200
    upsert.assert_awaited_once()
    args, kwargs = upsert.await_args
    assert args[0] == 504544  # deviation_id
    assert args[1] == 0  # task_index
    assert args[2] == 1  # attempt_number (first upload)
    assert kwargs["is_gospel"] is False
    assert kwargs["uploaded_by"] == 7
    assert kwargs["critique_pending"] is True


def test_upload_task_report_409_when_all_previous_recommendations_were_rejected(client, monkeypatch):
    # NOTE: db/critique_state.py's compute_upload_state hardcodes next_upload_is_final=False in
    # every branch (confirmed by reading the whole function) -- including the "all rejected"
    # branch, which instead locks the report as complete immediately. So an all-rejected report
    # can never actually reach a "gospel" reupload in the current code, despite the module
    # docstring describing exactly that as the intended behavior, and despite both this router and
    # rc_capa_critique.py's upload handlers reading state["next_upload_is_final"] to decide
    # is_gospel. This test documents the REAL current behavior (locked, 409) rather than the
    # apparently-intended one -- flagged to the user as a likely dead-code/bug, not fixed here.
    rejected_report = _report(
        attempt_number=2,
        recommendations=[{"id": 1, "description": "x", "decision": "rejected", "reason": "not applicable"}],
    )
    _mock_upload_chain(monkeypatch, report=rejected_report)
    upsert = AsyncMock(return_value=42)
    monkeypatch.setattr(module, "upsert_report", upsert)
    response = client.post("/task-critique/504544/none/sections/0/upload", files={"file": ("r.docx", b"x", "application/octet-stream")})
    assert response.status_code == 409
    upsert.assert_not_called()


# ---------------------------------------------------------------------------
# POST /{record_id}/{rci_id}/sections/{task_index}/recommendations/{recommendation_id}/decision
# ---------------------------------------------------------------------------


def test_decide_recommendation_requires_reason_when_rejected(client):
    response = client.post(
        "/task-critique/504544/none/sections/0/recommendations/1/decision",
        json={"decision": "rejected"},
    )
    assert response.status_code == 400
    assert "reason is required" in response.json()["detail"]


def test_decide_recommendation_404_when_no_source_document(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "fetch_source_document", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "fetch_latest_rci_plan_export_docx", AsyncMock(return_value=None))
    response = client.post(
        "/task-critique/504544/none/sections/0/recommendations/1/decision",
        json={"decision": "accepted"},
    )
    assert response.status_code == 404


def test_decide_recommendation_409_when_no_report_yet(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "fetch_source_document", AsyncMock(return_value=(b"manual", "manual.docx")))
    monkeypatch.setattr(module, "extract_task_sections", lambda b: [_section()])
    monkeypatch.setattr(module, "fetch_reports_by_task_index", AsyncMock(return_value={}))
    response = client.post(
        "/task-critique/504544/none/sections/0/recommendations/1/decision",
        json={"decision": "accepted"},
    )
    assert response.status_code == 409


def test_decide_recommendation_404_when_recommendation_id_unknown(client, monkeypatch):
    report = _report(recommendations=[{"id": 1, "description": "x", "decision": "pending", "reason": None}])
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "fetch_source_document", AsyncMock(return_value=(b"manual", "manual.docx")))
    monkeypatch.setattr(module, "extract_task_sections", lambda b: [_section()])
    monkeypatch.setattr(module, "fetch_reports_by_task_index", AsyncMock(return_value={0: report}))
    response = client.post(
        "/task-critique/504544/none/sections/0/recommendations/999/decision",
        json={"decision": "accepted"},
    )
    assert response.status_code == 404


def test_decide_recommendation_success_updates_decision(client, monkeypatch):
    report = _report(recommendations=[{"id": 1, "description": "x", "decision": "pending", "reason": None}])
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "fetch_source_document", AsyncMock(return_value=(b"manual", "manual.docx")))
    monkeypatch.setattr(module, "extract_task_sections", lambda b: [_section()])
    monkeypatch.setattr(module, "fetch_reports_by_task_index", AsyncMock(return_value={0: report}))
    set_decision = AsyncMock()
    monkeypatch.setattr(module, "set_recommendation_decision", set_decision)
    response = client.post(
        "/task-critique/504544/none/sections/0/recommendations/1/decision",
        json={"decision": "accepted"},
    )
    assert response.status_code == 200
    set_decision.assert_awaited_once()
    args, kwargs = set_decision.await_args
    assert args[0] == 504544
    assert args[1] == 0
    assert args[2] == 1
    assert args[3] == "accepted"


def test_decide_recommendation_rescores_when_rejecting_locks_the_report(client, monkeypatch):
    # Before decision: one pending recommendation. After decision (mocked as already-rejected via the
    # updated fetch_reports_by_task_index side_effect), it's the only one and all-rejected -> locks as
    # complete with no score yet, so the handler must trigger a rescore.
    before = _report(recommendations=[{"id": 1, "description": "x", "decision": "pending", "reason": None}])
    after = _report(recommendations=[{"id": 1, "description": "x", "decision": "rejected", "reason": "no"}], task_score=None)
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    monkeypatch.setattr(module, "fetch_source_document", AsyncMock(return_value=(b"manual", "manual.docx")))
    monkeypatch.setattr(module, "extract_task_sections", lambda b: [_section()])
    monkeypatch.setattr(
        module, "fetch_reports_by_task_index",
        AsyncMock(side_effect=[{0: before}, {0: after}, {0: after}]),
    )
    monkeypatch.setattr(module, "set_recommendation_decision", AsyncMock())
    monkeypatch.setattr(module, "fetch_report_file_bytes", AsyncMock(return_value=b"filebytes"))
    score_mock = AsyncMock(return_value=(88, [], False))
    monkeypatch.setattr(module, "_score_task_report", score_mock)
    set_score = AsyncMock()
    monkeypatch.setattr(module, "set_task_score", set_score)

    response = client.post(
        "/task-critique/504544/none/sections/0/recommendations/1/decision",
        json={"decision": "rejected", "reason": "not applicable"},
    )
    assert response.status_code == 200
    score_mock.assert_awaited_once()
    set_score.assert_awaited_once()
    args, _ = set_score.await_args
    assert args[0] == after["id"]
    assert args[1] == 88


# ---------------------------------------------------------------------------
# GET /{record_id}/{rci_id}/sections/{task_index}/history
# ---------------------------------------------------------------------------


def test_get_recommendation_history(client, monkeypatch):
    monkeypatch.setattr(module, "fetch_investigation_row", AsyncMock(return_value=_row()))
    history = [
        {
            "attempt_number": 2,
            "summary": "second attempt",
            "recommendations": [{"id": 1, "description": "x", "decision": "accepted", "reason": None}],
            "created_at": datetime.datetime(2026, 1, 2),
        },
        {"attempt_number": 1, "summary": None, "recommendations": [], "created_at": datetime.datetime(2026, 1, 1)},
    ]
    monkeypatch.setattr(module, "fetch_recommendation_history", AsyncMock(return_value=history))
    response = client.get("/task-critique/504544/none/sections/0/history")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["attempt_number"] == 2


# ---------------------------------------------------------------------------
# Pure/private helper functions, exercised directly (no HTTP layer)
# ---------------------------------------------------------------------------


def test_find_task_returns_matching_section():
    sections = [{"task_index": 0, "title": "A"}, {"task_index": 1, "title": "B"}]
    assert module._find_task(sections, 1)["title"] == "B"


def test_find_task_raises_404_when_missing():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        module._find_task([{"task_index": 0, "title": "A"}], 5)
    assert excinfo.value.status_code == 404


def test_describe_task_includes_correlation_and_checklist():
    description = module._describe_task(_section(title="Investigate seal", correlation="high priority", tasks=["Check seal"]))
    assert "Task: Investigate seal" in description
    assert "Correlation: high priority" in description
    assert "- Check seal" in description


def test_describe_task_omits_absent_optional_parts():
    description = module._describe_task({"title": "T", "correlation": None, "tasks": []})
    assert description == "Task: T"


def test_build_section_response_reflects_critique_failed_flag():
    section = {**_section(), "task_index": 0, "report": _report(critique_failed=True)}
    response = module._build_section_response(section)
    # TaskCritiqueSection has no critique_failed field of its own (only TaskCritiqueReport does) --
    # the kwarg _build_section_response passes is silently dropped by pydantic's default
    # extra="ignore"; the real signal lives on latest_report instead.
    assert response.latest_report.critique_failed is True


def test_build_section_response_with_no_report_yet():
    section = {**_section(), "task_index": 0, "report": None}
    response = module._build_section_response(section)
    assert response.status == "pending"
    assert response.latest_report is None


class _FakeDsResponse:
    def __init__(self, status_code=200, payload=None, raise_exc=None):
        self.status_code = status_code
        self._payload = payload or {}
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc

    def json(self):
        return self._payload


class _FakeDsClient:
    def __init__(self, response=None, post_exc=None):
        self._response = response
        self._post_exc = post_exc

    async def post(self, *args, **kwargs):
        if self._post_exc:
            raise self._post_exc
        return self._response


@pytest.mark.asyncio
async def test_score_task_report_returns_rounded_percentage_on_success(monkeypatch):
    client = _FakeDsClient(response=_FakeDsResponse(payload={
        "task_report_execution": {"percentage": 87.6},
        "info": [{"section": "task_report", "id": "x"}, {"section": "capa", "id": "y"}],
    }))
    monkeypatch.setattr(module, "get_client", lambda: client)
    score, info, failed = await module._score_task_report("Deviation", "r.docx", b"bytes", "application/octet-stream")
    assert score == 88
    assert failed is False
    assert info == [{"section": "task_report", "id": "x"}]  # capa-section table filtered out


@pytest.mark.asyncio
async def test_score_task_report_marks_failed_on_http_error():
    import httpx

    client = _FakeDsClient(post_exc=httpx.ConnectError("refused", request=httpx.Request("POST", "http://ds")))
    import unittest.mock as mock
    with mock.patch.object(module, "get_client", return_value=client):
        score, info, failed = await module._score_task_report("Deviation", "r.docx", b"bytes", None)
    assert score is None
    assert info == []
    assert failed is True


@pytest.mark.asyncio
async def test_score_task_report_marks_failed_when_no_task_report_section_detected():
    import unittest.mock as mock

    client = _FakeDsClient(response=_FakeDsResponse(payload={"task_report_execution": None, "info": []}))
    with mock.patch.object(module, "get_client", return_value=client):
        score, info, failed = await module._score_task_report("Deviation", "r.docx", b"bytes", None)
    assert score is None
    assert failed is True


@pytest.mark.asyncio
async def test_score_task_report_raises_on_truthy_but_malformed_task_report_execution():
    # NOTE (likely bug, not fixed here): the comment at backend/routers/task_critique.py:83-86
    # claims a malformed 200 response is "treat[ed] ... the same as a scoring failure" via the
    # `except (ValueError, KeyError, TypeError)` clause, but `task_report_execution["percentage"]`
    # is evaluated AFTER that try/except block has already exited (see line 94), so a dict that's
    # truthy but missing "percentage" raises an uncaught KeyError instead of degrading gracefully.
    # This documents the real current behavior; a genuinely malformed (non-JSON) body IS caught,
    # since that KeyError/ValueError happens inside the try block at response.json()/data.get(...).
    import unittest.mock as mock

    client = _FakeDsClient(response=_FakeDsResponse(payload={"task_report_execution": {"wrong_key": 1}}))
    with mock.patch.object(module, "get_client", return_value=client):
        with pytest.raises(KeyError):
            await module._score_task_report("Deviation", "r.docx", b"bytes", None)
