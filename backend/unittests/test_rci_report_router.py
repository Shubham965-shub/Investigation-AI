"""Router-level tests for backend.routers.rci_report — DB/DS-client layer entirely mocked, no live DB or network.

RciReportSections has every section Optional except event_type (plus annexures/approval/errors,
which all default), so {"event_type": "..."} alone is a valid minimal instance — no need to hand-build
the full nested schema for most tests.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.auth import get_current_payload, get_current_username
from backend.routers.rci_report import router


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
    monkeypatch.setattr(f"backend.routers.rci_report.{name}", value)


def _investigation_row(qe_type="Deviation"):
    return {"qe_type": qe_type, "investigator": "Jane Doe", "rci_number": "RCI-1"}


# ---------------------------------------------------------------------------
# GET /{record_id}/{rci_id}
# ---------------------------------------------------------------------------


def test_get_rci_report_rejects_non_numeric_record_id(client):
    response = client.get("/rci-report/not-a-number/none")
    assert response.status_code == 404


def test_get_rci_report_404s_when_investigation_not_found(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=None))
    response = client.get("/rci-report/504544/none")
    assert response.status_code == 404


def test_get_rci_report_returns_empty_shape_when_nothing_generated_yet(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    _patch(monkeypatch, "fetch_rci_report", AsyncMock(return_value=None))

    response = client.get("/rci-report/504544/none")
    assert response.status_code == 200
    body = response.json()
    assert body["report"] is None
    assert body["generated_at"] is None
    assert body["mc_confirmed"] is None
    assert body["manual_entries"] == {}


def test_get_rci_report_returns_stored_report(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    _patch(
        monkeypatch,
        "fetch_rci_report",
        AsyncMock(
            return_value={
                "report": {"event_type": "Deviation"},
                "generated_at": "2026-01-01T00:00:00",
                "mc_confirmed": True,
                "manual_entries": {"process_flow": "Step 1 -> Step 2"},
            }
        ),
    )

    response = client.get("/rci-report/504544/none")
    assert response.status_code == 200
    body = response.json()
    assert body["report"]["event_type"] == "Deviation"
    assert body["mc_confirmed"] is True
    assert body["manual_entries"] == {"process_flow": "Step 1 -> Step 2"}


# ---------------------------------------------------------------------------
# PUT /{record_id}/{rci_id}/inputs
# ---------------------------------------------------------------------------


def test_update_rci_report_inputs_rejects_non_numeric_record_id(client):
    response = client.put("/rci-report/not-a-number/none/inputs", json={"manual_entries": {}})
    assert response.status_code == 404


def test_update_rci_report_inputs_happy_path(client, monkeypatch):
    save_mock = AsyncMock()
    _patch(monkeypatch, "save_rci_report_inputs", save_mock)
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    _patch(monkeypatch, "fetch_rci_report", AsyncMock(return_value=None))

    response = client.put(
        "/rci-report/504544/none/inputs",
        json={"mc_confirmed": True, "manual_entries": {"process_flow": "A -> B"}},
    )
    assert response.status_code == 200
    save_mock.assert_awaited_once()
    assert save_mock.call_args.args[0] == 504544
    assert save_mock.call_args.args[1] is True
    assert save_mock.call_args.args[2] == {"process_flow": "A -> B"}


# ---------------------------------------------------------------------------
# POST /{record_id}/{rci_id}/generate
# ---------------------------------------------------------------------------


def test_generate_rci_report_rejects_non_numeric_record_id(client):
    response = client.post("/rci-report/not-a-number/none/generate")
    assert response.status_code == 404


def test_generate_rci_report_404s_when_investigation_not_found(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=None))
    response = client.post("/rci-report/504544/none/generate")
    assert response.status_code == 404


def _full_stored(**overrides):
    base = {"report": None, "generated_at": None, "mc_confirmed": None, "manual_entries": {}}
    base.update(overrides)
    return base


def _patch_generate_common(monkeypatch, *, stored=None, rci_sections=None, problem_statement=None):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    _patch(monkeypatch, "fetch_rci_report", AsyncMock(return_value=stored))
    _patch(monkeypatch, "fetch_rci_sections", AsyncMock(return_value=rci_sections or []))
    _patch(monkeypatch, "fetch_reports_by_task_index", AsyncMock(return_value={}))
    _patch(monkeypatch, "fetch_rc_capa_reports", AsyncMock(return_value=[]))
    _patch(monkeypatch, "fetch_problem_statement", AsyncMock(return_value=problem_statement))
    _patch(monkeypatch, "save_rci_report", AsyncMock())


def test_generate_rci_report_happy_path(client, monkeypatch):
    _patch_generate_common(monkeypatch, stored=_full_stored(mc_confirmed=True))
    ds_post = AsyncMock(return_value={"event_type": "Deviation"})
    _patch(monkeypatch, "ds_post", ds_post)

    response = client.post("/rci-report/504544/none/generate")
    assert response.status_code == 200
    sent_payload = ds_post.call_args.kwargs["json"]
    assert sent_payload["deviation_id"] == "504544"
    assert sent_payload["event_type"] == "Deviation"
    assert sent_payload["mc_confirmed"] is True


def test_generate_rci_report_overwrites_executive_summary_problem_description_with_approved_ps(client, monkeypatch):
    _patch_generate_common(monkeypatch, stored=None, problem_statement="The approved problem statement.")
    executive_summary = {
        "summary": ["s"],
        "problem_description": ["ds's own re-derived description"],
        "immediate_containment_action": ["a"],
        "determination_of_root_cause": ["b"],
        "root_cause_probable_cause_statement": ["c"],
        "impact_assessment": ["d"],
        "correction_conclusion_preventive_actions": ["e"],
        "conclusion_statement": ["f"],
    }
    _patch(monkeypatch, "ds_post", AsyncMock(return_value={"event_type": "Deviation", "executive_summary": executive_summary}))
    save_mock = AsyncMock()
    _patch(monkeypatch, "save_rci_report", save_mock)

    response = client.post("/rci-report/504544/none/generate")
    assert response.status_code == 200
    saved_report = save_mock.call_args.args[1]
    assert saved_report["executive_summary"]["problem_description"] == ["The approved problem statement."]


def test_generate_rci_report_uses_latest_rc_capa_report(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    _patch(monkeypatch, "fetch_rci_report", AsyncMock(return_value=None))
    _patch(monkeypatch, "fetch_rci_sections", AsyncMock(return_value=[]))
    _patch(monkeypatch, "fetch_reports_by_task_index", AsyncMock(return_value={}))
    older = {"critiques": [{"category": "capa", "summary": "old", "recommendations": []}]}
    newer = {"critiques": [{"category": "capa", "summary": "newest", "recommendations": []}]}
    _patch(monkeypatch, "fetch_rc_capa_reports", AsyncMock(return_value=[older, newer]))
    _patch(monkeypatch, "fetch_problem_statement", AsyncMock(return_value=None))
    _patch(monkeypatch, "save_rci_report", AsyncMock())
    ds_post = AsyncMock(return_value={"event_type": "Deviation"})
    _patch(monkeypatch, "ds_post", ds_post)

    response = client.post("/rci-report/504544/none/generate")
    assert response.status_code == 200
    sent_payload = ds_post.call_args.kwargs["json"]
    assert sent_payload["accepted_capa"]["capa_overall_text"] == "newest"


# ---------------------------------------------------------------------------
# PUT /{record_id}/{rci_id}
# ---------------------------------------------------------------------------


def test_update_rci_report_rejects_non_numeric_record_id(client):
    response = client.put("/rci-report/not-a-number/none", json={"event_type": "Deviation"})
    assert response.status_code == 404


def test_update_rci_report_404s_when_nothing_generated_yet(client, monkeypatch):
    _patch(monkeypatch, "fetch_rci_report", AsyncMock(return_value=None))
    response = client.put("/rci-report/504544/none", json={"event_type": "Deviation"})
    assert response.status_code == 404


def test_update_rci_report_404s_when_stored_report_is_none(client, monkeypatch):
    _patch(monkeypatch, "fetch_rci_report", AsyncMock(return_value={"report": None}))
    response = client.put("/rci-report/504544/none", json={"event_type": "Deviation"})
    assert response.status_code == 404


def test_update_rci_report_happy_path(client, monkeypatch):
    _patch(
        monkeypatch,
        "fetch_rci_report",
        AsyncMock(return_value=_full_stored(report={"event_type": "Deviation"})),
    )
    update_mock = AsyncMock()
    _patch(monkeypatch, "update_rci_report_sections", update_mock)
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    _patch(monkeypatch, "fetch_problem_statement", AsyncMock(return_value=None))

    response = client.put("/rci-report/504544/none", json={"event_type": "Deviation"})
    assert response.status_code == 200
    update_mock.assert_awaited_once()
    assert update_mock.call_args.args[0] == 504544


# ---------------------------------------------------------------------------
# GET /{record_id}/{rci_id}/export
# ---------------------------------------------------------------------------


def test_export_rci_report_rejects_non_numeric_record_id(client):
    response = client.get("/rci-report/not-a-number/none/export")
    assert response.status_code == 404


def test_export_rci_report_404s_when_investigation_not_found(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=None))
    response = client.get("/rci-report/504544/none/export")
    assert response.status_code == 404


def test_export_rci_report_404s_when_nothing_generated_yet(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    _patch(monkeypatch, "fetch_rci_report", AsyncMock(return_value=None))
    response = client.get("/rci-report/504544/none/export")
    assert response.status_code == 404


def test_export_rci_report_happy_path_derives_team_members_and_dedupes(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    _patch(
        monkeypatch,
        "fetch_rci_report",
        AsyncMock(
            return_value={
                "report": {"event_type": "Deviation"},
                "manual_entries": {"process_flow": "A -> B"},
            }
        ),
    )
    _patch(
        monkeypatch,
        "fetch_rci_sections",
        AsyncMock(
            return_value=[
                {"title": "Section A", "assignee": "Jane Doe"},  # same as investigator — must not duplicate
                {"title": "Section B", "assignee": "John Smith"},
                {"title": "Section C", "assignee": None},
            ]
        ),
    )
    build_docx_mock = MagicMock(return_value=b"fake report bytes")
    _patch(monkeypatch, "build_rci_report_docx", build_docx_mock)
    _patch(monkeypatch, "fetch_user_by_username", AsyncMock(return_value={"id": 42}))
    insert_mock = AsyncMock()
    _patch(monkeypatch, "insert_rci_report_export", insert_mock)

    response = client.get("/rci-report/504544/none/export")

    assert response.status_code == 200
    assert response.content == b"fake report bytes"
    assert "RCI_Report_504544.docx" in response.headers["content-disposition"]

    call_args = build_docx_mock.call_args.args
    team_members = call_args[4]
    assert team_members == [("Jane Doe", "Investigator"), ("John Smith", "Section B")]
    manual_entries_arg = call_args[5]
    assert manual_entries_arg == {"process_flow": "A -> B"}
    insert_mock.assert_awaited_once()
    assert insert_mock.call_args.args[2] == 42


def test_export_rci_report_persist_failure_does_not_block_download(client, monkeypatch):
    _patch(monkeypatch, "fetch_investigation_row", AsyncMock(return_value=_investigation_row()))
    _patch(
        monkeypatch,
        "fetch_rci_report",
        AsyncMock(return_value={"report": {"event_type": "Deviation"}, "manual_entries": {}}),
    )
    _patch(monkeypatch, "fetch_rci_sections", AsyncMock(return_value=[]))
    _patch(monkeypatch, "build_rci_report_docx", MagicMock(return_value=b"fake report bytes"))
    _patch(monkeypatch, "fetch_user_by_username", AsyncMock(side_effect=RuntimeError("db down")))
    _patch(monkeypatch, "insert_rci_report_export", AsyncMock())

    response = client.get("/rci-report/504544/none/export")
    assert response.status_code == 200
    assert response.content == b"fake report bytes"
