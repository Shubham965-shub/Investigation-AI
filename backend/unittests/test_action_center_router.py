"""Tests for backend/backend/routers/action_center.py — no live DB.

Two layers:
1. Direct unit tests of the module's pure helper functions (date bucketing, product
   extraction/resolution, due-date formatting) — no FastAPI/TestClient needed.
2. A handful of TestClient-based scenarios for the two endpoints, with every DB query
   function monkeypatched (patched on backend.routers.action_center, where they're
   imported into, not on their defining module)."""

import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from backend.routers import action_center as ac
from backend.routers.auth import issue_token

# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


def test_month_starts_returns_n_months_oldest_first_including_current():
    months = ac._month_starts(3, datetime.date(2026, 3, 15))
    assert months == [datetime.date(2026, 1, 1), datetime.date(2026, 2, 1), datetime.date(2026, 3, 1)]


def test_bucket_monthly_counts_rows_per_month_and_converts_datetime_to_date():
    months = [datetime.date(2026, 1, 1), datetime.date(2026, 2, 1)]
    rows = [
        {"date_opened": datetime.datetime(2026, 1, 5, 10, 30)},
        {"date_opened": datetime.date(2026, 1, 20)},
        {"date_opened": datetime.date(2026, 2, 1)},
        {"date_opened": None},
    ]
    bars = ac._bucket_monthly(rows, "date_opened", months)
    assert [(b.label, b.count) for b in bars] == [("Jan", 2), ("Feb", 1)]


def test_bucket_monthly_ignores_rows_outside_the_window():
    months = [datetime.date(2026, 2, 1)]
    rows = [{"date_opened": datetime.date(2026, 1, 1)}]
    bars = ac._bucket_monthly(rows, "date_opened", months)
    assert bars[0].count == 0


def test_trend_percent_none_when_fewer_than_two_months_or_prior_is_zero():
    assert ac._trend_percent([ac.MonthlyBar(label="Jan", count=5)]) is None
    assert ac._trend_percent([ac.MonthlyBar(label="Jan", count=0), ac.MonthlyBar(label="Feb", count=5)]) is None


def test_trend_percent_computes_rounded_percent_change():
    bars = [ac.MonthlyBar(label="Jan", count=10), ac.MonthlyBar(label="Feb", count=15)]
    assert ac._trend_percent(bars) == 50


def test_fmt_date_formats_or_returns_none():
    assert ac._fmt_date(datetime.date(2026, 1, 5)) == "05 Jan 2026"
    assert ac._fmt_date(None) is None


def test_fmt_due_date_display_formats_plain_date():
    assert ac._fmt_due_date_display("01/15/2026") == "15 Jan 2026"


def test_fmt_due_date_display_preserves_extension_marker():
    assert ac._fmt_due_date_display("01/15/2026(EXT)") == "15 Jan 2026 (EXT)"


def test_fmt_due_date_display_none_passthrough():
    assert ac._fmt_due_date_display(None) is None
    assert ac._fmt_due_date_display("") is None


def test_bucket_for_maps_known_statuses_and_defaults_to_unassigned():
    assert ac._bucket_for("On Track") == "on_track"
    assert ac._bucket_for("At Risk") == "delay"
    assert ac._bucket_for("Overdue") == "overdue"
    assert ac._bucket_for("Unassigned") == "unassigned"
    assert ac._bucket_for("Something Else") == "unassigned"
    assert ac._bucket_for(None) == "unassigned"


def test_parse_investigator_by_rci_parses_json_string():
    assert ac._parse_investigator_by_rci('{"504544": "Jane Doe"}') == {"504544": "Jane Doe"}


def test_parse_investigator_by_rci_empty_for_none_or_blank():
    assert ac._parse_investigator_by_rci(None) == {}
    assert ac._parse_investigator_by_rci("") == {}


def test_extract_product_from_title_market_complaint():
    title = "Paracetamol 500mg; B.No. B12345 reported defective"
    assert ac._extract_product_from_title(title, "Market Complaint") == "Paracetamol 500mg"


def test_extract_product_from_title_oos_picks_the_longest_segment():
    title = "Assay OOS for batch B.No: B12345 - Paracetamol 500mg Tablets - US"
    result = ac._extract_product_from_title(title, "OOS")
    assert result == "Paracetamol 500mg Tablets"


def test_extract_product_from_title_returns_none_for_deviation_type():
    assert ac._extract_product_from_title("Some deviation title", "Deviation") is None


def test_extract_product_from_title_returns_none_for_blank_title():
    assert ac._extract_product_from_title(None, "OOS") is None
    assert ac._extract_product_from_title("", "OOS") is None


def test_resolve_product_prefers_raw_product_when_meaningful():
    assert ac._resolve_product("Paracetamol", "irrelevant title", "Deviation") == "Paracetamol"


def test_resolve_product_falls_back_to_title_extraction_when_not_applicable():
    title = "Paracetamol 500mg; B.No. B12345 reported defective"
    assert ac._resolve_product("Not Applicable", title, "Market Complaint") == "Paracetamol 500mg"


def test_resolve_product_falls_back_to_raw_when_title_extraction_fails():
    assert ac._resolve_product("Not Applicable", None, "Deviation") == "Not Applicable"


# ---------------------------------------------------------------------------
# TestClient-based endpoint tests
# ---------------------------------------------------------------------------

app = FastAPI()
app.include_router(ac.router)
client = TestClient(app)


def _open_row(**overrides):
    row = {
        "deviation_id": 1,
        "title": "Pump seal deviation",
        "qe_type": "Deviation",
        "investigator": "Jane Doe",
        "location": "Site A",
        "department": "Production",
        "product": "Paracetamol",
        "criticality": "Non-Critical",
        "event_classification": None,
        "oos_oot_phase": None,
        "escalation_level": None,
        "due_date_display": "01/15/2026",
        "extended_due_date": None,
        "due_date": datetime.datetime(2026, 1, 15),
        "date_opened": datetime.datetime(2026, 1, 1),
        "pg_updated_at_timestamp": datetime.datetime(2026, 1, 2),
        "module": "Problem Statement",
        "module_risk_status": "Closed",
        "open_investigation_status": "On Track",
        "rci_ids": [],
        "investigator_by_rci": None,
    }
    row.update(overrides)
    return row


def _mock_summary_deps(monkeypatch, open_rows=None, cancelled_rows=None, departments=None, remarks=None, stages=None, trend_rows=None):
    monkeypatch.setattr(ac, "fetch_open_investigations", AsyncMock(return_value=open_rows or []))
    monkeypatch.setattr(ac, "fetch_cancelled_investigations", AsyncMock(return_value=cancelled_rows or []))
    monkeypatch.setattr(ac, "fetch_all_departments", AsyncMock(return_value=departments or []))
    monkeypatch.setattr(ac, "fetch_remarks", AsyncMock(return_value=remarks or {}))
    monkeypatch.setattr(ac, "fetch_investigator_progress_stage", AsyncMock(return_value=stages or {}))
    monkeypatch.setattr(ac, "fetch_monthly_trend_rows", AsyncMock(return_value=trend_rows or []))


def _token(roles=None, investigator_name=None):
    return issue_token("user@example.com", 1, roles=roles or [], investigator_name=investigator_name)


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_summary_requires_auth():
    response = client.get("/action-center/summary")
    assert response.status_code == 401


def test_summary_happy_path_returns_one_investigation(monkeypatch):
    _mock_summary_deps(monkeypatch, open_rows=[_open_row()])
    response = client.get("/action-center/summary", headers=_auth_headers(_token(roles=["Admin"])))
    assert response.status_code == 200
    body = response.json()
    assert body["total_investigations"] == 1
    assert body["investigations"][0]["title"] == "Pump seal deviation"
    assert body["investigations"][0]["total_stages"] == 6


def test_summary_filters_by_site(monkeypatch):
    rows = [_open_row(deviation_id=1, location="Site A"), _open_row(deviation_id=2, location="Site B")]
    _mock_summary_deps(monkeypatch, open_rows=rows)
    response = client.get("/action-center/summary?site=Site A", headers=_auth_headers(_token(roles=["Admin"])))
    body = response.json()
    assert body["total_investigations"] == 1
    assert body["investigations"][0]["site"] == "Site A"


def test_summary_filters_by_unassigned_investigator(monkeypatch):
    rows = [_open_row(deviation_id=1, investigator="Jane Doe"), _open_row(deviation_id=2, investigator=None)]
    _mock_summary_deps(monkeypatch, open_rows=rows)
    response = client.get(
        "/action-center/summary?investigator=__unassigned__", headers=_auth_headers(_token(roles=["Admin"]))
    )
    body = response.json()
    assert body["total_investigations"] == 1
    assert body["investigations"][0]["investigator"] is None


def test_summary_criticality_filter(monkeypatch):
    rows = [_open_row(deviation_id=1, criticality="Critical"), _open_row(deviation_id=2, criticality="Non-Critical")]
    _mock_summary_deps(monkeypatch, open_rows=rows)
    response = client.get("/action-center/summary?criticality=critical", headers=_auth_headers(_token(roles=["Admin"])))
    body = response.json()
    assert body["total_investigations"] == 1
    assert body["investigations"][0]["criticality"] == "Critical"


def test_summary_status_cancelled_toggle_returns_only_cancelled_rows(monkeypatch):
    open_rows = [_open_row(deviation_id=1)]
    cancelled_rows = [_open_row(deviation_id=2, title="Cancelled deviation")]
    _mock_summary_deps(monkeypatch, open_rows=open_rows, cancelled_rows=cancelled_rows)
    response = client.get("/action-center/summary?status=cancelled", headers=_auth_headers(_token(roles=["Admin"])))
    body = response.json()
    # Cancelled rows never affect total_investigations (still open-only).
    assert body["total_investigations"] == 1
    assert len(body["investigations"]) == 1
    assert body["investigations"][0]["title"] == "Cancelled deviation"
    assert body["investigations"][0]["is_cancelled"] is True


def test_summary_investigator_role_scopes_to_own_rci_only(monkeypatch):
    # Two RCIs on one deviation, each with a different investigator. The Investigator-role
    # caller must only see their own RCI, not their colleague's, on the same deviation row.
    rows = [
        _open_row(
            deviation_id=1,
            rci_ids=["504544", "504545"],
            investigator="Jane Doe",
            investigator_by_rci='{"504544": "Jane Doe", "504545": "John Smith"}',
        )
    ]
    _mock_summary_deps(monkeypatch, open_rows=rows)
    response = client.get(
        "/action-center/summary",
        headers=_auth_headers(_token(roles=["Investigator"], investigator_name="Jane Doe")),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_investigations"] == 1
    assert body["investigations"][0]["rci_ids"] == ["504544"]


def test_summary_investigator_role_excludes_deviations_with_no_matching_rci(monkeypatch):
    rows = [
        _open_row(
            deviation_id=1,
            investigator="John Smith",
            investigator_by_rci='{"504544": "John Smith"}',
            rci_ids=["504544"],
        )
    ]
    _mock_summary_deps(monkeypatch, open_rows=rows)
    response = client.get(
        "/action-center/summary",
        headers=_auth_headers(_token(roles=["Investigator"], investigator_name="Jane Doe")),
    )
    body = response.json()
    assert body["total_investigations"] == 0


# ---------------------------------------------------------------------------
# PUT /action-center/{record_id}/remark
# ---------------------------------------------------------------------------


def test_update_remark_requires_sit_role():
    response = client.put(
        "/action-center/1/remark",
        json={"rci_id": "", "remark": "Looks fine"},
        headers=_auth_headers(_token(roles=["Investigator"])),
    )
    assert response.status_code == 403


def test_update_remark_succeeds_for_sit(monkeypatch):
    save_mock = AsyncMock()
    monkeypatch.setattr(ac, "save_remark", save_mock)
    response = client.put(
        "/action-center/1/remark",
        json={"rci_id": "504544", "remark": "Looks fine"},
        headers=_auth_headers(_token(roles=["SIT"])),
    )
    assert response.status_code == 200
    assert response.json() == {"remark": "Looks fine"}
    save_mock.assert_awaited_once_with(1, "504544", "Looks fine")


def test_update_remark_rejects_non_numeric_record_id(monkeypatch):
    monkeypatch.setattr(ac, "save_remark", AsyncMock())
    response = client.put(
        "/action-center/not-a-number/remark",
        json={"rci_id": "", "remark": "Looks fine"},
        headers=_auth_headers(_token(roles=["SIT"])),
    )
    assert response.status_code == 404
