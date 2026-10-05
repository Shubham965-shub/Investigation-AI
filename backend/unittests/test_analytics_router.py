"""Router-level tests for backend/routers/analytics.py — fetch_analytics_rows is mocked; the
real aggregation/filtering/trend logic in the handler runs for real against in-memory rows."""
import datetime

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import analytics as analytics_router


def _make_client():
    app = FastAPI()
    app.include_router(analytics_router.router)
    return TestClient(app)


def _row(**overrides):
    row = {
        "deviation_id": 1,
        "date_opened": datetime.datetime(2026, 9, 15),
        "capa_record_id": None,
        "qe_type": "Deviation",
        "open_investigation_status": "Open",
        "root_cause_category": None,
        "root_cause_broad_category": None,
        "product": "Paracetamol",
        "equipment": "Tablet Press",
        "site": "Site A",
        "department": "Production",
        "pg_updated_at_timestamp": datetime.datetime(2026, 9, 20, 10, 0, 0),
    }
    row.update(overrides)
    return row


def test_summary_happy_path_shape(monkeypatch):
    monkeypatch.setattr(analytics_router, "fetch_analytics_rows", AsyncMock(return_value=[_row()]))
    client = _make_client()

    response = client.get("/analytics/summary")

    assert response.status_code == 200
    body = response.json()
    assert {e["key"] for e in body["events"]} == {"overall", "deviation", "oos", "oot", "market_complaint"}
    overall = next(e for e in body["events"] if e["key"] == "overall")
    assert overall["total"] == 1
    assert body["last_updated_at"] is not None


def test_overdue_pct_is_zero_when_no_rows_of_that_type(monkeypatch):
    monkeypatch.setattr(analytics_router, "fetch_analytics_rows", AsyncMock(return_value=[]))
    client = _make_client()
    response = client.get("/analytics/summary")
    overall = next(e for e in response.json()["events"] if e["key"] == "overall")
    assert overall["total"] == 0
    assert overall["overdue_pct"] == 0


def test_overdue_pct_computed_correctly(monkeypatch):
    rows = [
        _row(deviation_id=1, open_investigation_status="Overdue"),
        _row(deviation_id=2, open_investigation_status="Closed"),
        _row(deviation_id=3, open_investigation_status="Open"),
        _row(deviation_id=4, open_investigation_status="Overdue"),
    ]
    monkeypatch.setattr(analytics_router, "fetch_analytics_rows", AsyncMock(return_value=rows))
    client = _make_client()
    response = client.get("/analytics/summary")
    overall = next(e for e in response.json()["events"] if e["key"] == "overall")
    assert overall["total"] == 4
    assert overall["closed"] == 1
    assert overall["overdue"] == 2
    assert overall["in_progress"] == 3  # total - closed
    assert overall["overdue_pct"] == 50


def test_qe_type_labels_map_into_event_type_cards(monkeypatch):
    rows = [
        _row(deviation_id=1, qe_type="Out Of Specification"),
        _row(deviation_id=2, qe_type="Out of Trend"),
        _row(deviation_id=3, qe_type="Complaint"),
    ]
    monkeypatch.setattr(analytics_router, "fetch_analytics_rows", AsyncMock(return_value=rows))
    client = _make_client()
    response = client.get("/analytics/summary")
    by_key = {e["key"]: e for e in response.json()["events"]}
    assert by_key["oos"]["total"] == 1
    assert by_key["oot"]["total"] == 1
    assert by_key["market_complaint"]["total"] == 1
    assert by_key["deviation"]["total"] == 0


def test_categorical_filters_narrow_the_rows(monkeypatch):
    rows = [
        _row(deviation_id=1, site="Site A", product="Paracetamol"),
        _row(deviation_id=2, site="Site B", product="Ibuprofen"),
    ]
    monkeypatch.setattr(analytics_router, "fetch_analytics_rows", AsyncMock(return_value=rows))
    client = _make_client()

    response = client.get("/analytics/summary", params={"site": "Site A"})
    overall = next(e for e in response.json()["events"] if e["key"] == "overall")
    assert overall["total"] == 1

    # Filter options reflect the FULL unfiltered population even though rows above were filtered.
    assert response.json()["filter_options"]["sites"] == ["Site A", "Site B"]


def test_department_product_equipment_filters_each_narrow_the_rows(monkeypatch):
    rows = [
        _row(deviation_id=1, department="Production", product="Paracetamol", equipment="Tablet Press"),
        _row(deviation_id=2, department="QC", product="Ibuprofen", equipment="HPLC"),
    ]
    monkeypatch.setattr(analytics_router, "fetch_analytics_rows", AsyncMock(return_value=rows))
    client = _make_client()

    dept_response = client.get("/analytics/summary", params={"department": "QC"})
    assert next(e for e in dept_response.json()["events"] if e["key"] == "overall")["total"] == 1

    product_response = client.get("/analytics/summary", params={"product": "Paracetamol"})
    assert next(e for e in product_response.json()["events"] if e["key"] == "overall")["total"] == 1

    equipment_response = client.get("/analytics/summary", params={"equipment": "HPLC"})
    assert next(e for e in equipment_response.json()["events"] if e["key"] == "overall")["total"] == 1


def test_start_date_from_filters_rows_by_date_opened(monkeypatch):
    rows = [
        _row(deviation_id=1, date_opened=datetime.datetime(2026, 1, 1)),
        _row(deviation_id=2, date_opened=datetime.datetime(2026, 9, 1)),
    ]
    monkeypatch.setattr(analytics_router, "fetch_analytics_rows", AsyncMock(return_value=rows))
    client = _make_client()

    response = client.get("/analytics/summary", params={"start_date_from": "2026-06-01"})
    overall = next(e for e in response.json()["events"] if e["key"] == "overall")
    assert overall["total"] == 1


def test_not_applicable_product_and_equipment_values_are_excluded_from_filter_options_and_frequency(monkeypatch):
    rows = [
        _row(deviation_id=1, product="Not Applicable", equipment="N/A"),
        _row(deviation_id=2, product="Paracetamol", equipment="Tablet Press"),
    ]
    monkeypatch.setattr(analytics_router, "fetch_analytics_rows", AsyncMock(return_value=rows))
    client = _make_client()
    response = client.get("/analytics/summary")
    body = response.json()
    assert body["filter_options"]["products"] == ["Paracetamol"]
    assert body["filter_options"]["equipment"] == ["Tablet Press"]
    assert [p["label"] for p in body["failure_patterns"]["products"]] == ["Paracetamol"]


def test_non_assignable_root_cause_values_count_as_not_identified(monkeypatch):
    rows = [
        _row(deviation_id=1, root_cause_category="Non Assignable"),
        _row(deviation_id=2, root_cause_category=None),
        _row(deviation_id=3, root_cause_category="Handling"),
    ]
    monkeypatch.setattr(analytics_router, "fetch_analytics_rows", AsyncMock(return_value=rows))
    client = _make_client()
    response = client.get("/analytics/summary")
    rc_status = response.json()["root_cause_status"]
    assert rc_status["identified"] == 1
    assert rc_status["not_identified"] == 2
    assert rc_status["total"] == 3


def test_root_cause_category_maps_onto_6m_bucket(monkeypatch):
    rows = [_row(deviation_id=1, root_cause_category="Handling"), _row(deviation_id=2, root_cause_category="Instrument")]
    monkeypatch.setattr(analytics_router, "fetch_analytics_rows", AsyncMock(return_value=rows))
    client = _make_client()
    response = client.get("/analytics/summary")
    by_label = {c["label"]: c["count"] for c in response.json()["root_cause_categories"]}
    assert by_label["Man"] == 1
    assert by_label["Machine"] == 1
    assert by_label["Material"] == 0


def test_capa_status_splits_rows_with_and_without_capa(monkeypatch):
    rows = [
        _row(deviation_id=1, capa_record_id="CAPA-1"),
        _row(deviation_id=2, capa_record_id=None),
    ]
    monkeypatch.setattr(analytics_router, "fetch_analytics_rows", AsyncMock(return_value=rows))
    client = _make_client()
    response = client.get("/analytics/summary")
    capa = response.json()["capa"]
    assert capa["with_capa"] == 1
    assert capa["without_capa"] == 1
    assert capa["total"] == 2
    assert len(capa["monthly_trend"]) == 6


def test_last_updated_at_is_none_when_no_rows_have_a_timestamp(monkeypatch):
    rows = [_row(pg_updated_at_timestamp=None)]
    monkeypatch.setattr(analytics_router, "fetch_analytics_rows", AsyncMock(return_value=rows))
    client = _make_client()
    response = client.get("/analytics/summary")
    assert response.json()["last_updated_at"] is None
