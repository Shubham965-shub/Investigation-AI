import datetime

from backend.db.field_mapping import (
    build_trackwise_fields,
    normalize_rci_id,
    resolved_event_type,
)


def row(**kwargs):
    # build_trackwise_fields only ever calls row.get(col) — a plain dict stands in for asyncpg.Record.
    return kwargs


def test_deviation_basic_fields():
    fields = build_trackwise_fields(
        row(
            title="Pump seal failure",
            observed_by="J Smith",
            batch_no="B123",
            sfg_code="SFG-1",
            name_of_material="Paracetamol",
            deviation_to="QA",
            department="Production",
            instrument_equipment="Pump A",
            instrument_equipment_id="EQ-1",
            description="desc",
            investigator="Jane Doe",
            rci_number="RCI-1",
        ),
        "Deviation",
    )
    assert fields["title"] == "Pump seal failure"
    assert fields["Department"] == "Production"
    assert fields["Equipment Name"] == "Pump A"
    assert fields["Name of the Instrument"] == "Pump A"
    assert fields["Investigator"] == "Jane Doe"
    assert fields["RCI Number"] == "RCI-1"
    assert "Deviation Number" not in fields  # not requested as extended


def test_deviation_extended_fields_join_arrays_and_wrap_lists():
    fields = build_trackwise_fields(
        row(
            title="t",
            investigator="inv",
            rci_number="r1",
            deviation_number="D-1",
            date_opened=datetime.datetime(2026, 1, 5, 14, 30),
            related_market=["US", "EU"],
            related_customer=["Acme"],
            immediate_actions="stopped the line",
            impact_details="minor",
            proposal_for_resolution="retrain staff",
        ),
        "Deviation",
        extended=True,
    )
    assert fields["Date Opened"] == "2026-01-05"  # time component dropped
    assert fields["Related Market"] == "US, EU"  # joined for RCI Plan
    assert fields["Related Customer"] == "Acme"
    assert fields["Immediate Actions"] == ["stopped the line"]  # wrapped for RCI Plan
    assert fields["Impact Details"] == ["minor"]
    assert fields["Proposal for Resolution"] == ["retrain staff"]


def test_deviation_extended_for_rci_report_keeps_raw_shapes():
    fields = build_trackwise_fields(
        row(
            title="t",
            investigator="inv",
            rci_number="r1",
            related_market=["US", "EU"],
            related_customer=["Acme"],
            immediate_actions="stopped the line",
            impact_details="minor",
        ),
        "Deviation",
        extended=True,
        for_rci_report=True,
    )
    assert fields["Related Market"] == ["US", "EU"]  # list, not joined
    assert fields["Related Customer"] == ["Acme"]
    assert fields["Immediate Actions"] == "stopped the line"  # raw string, not wrapped
    assert fields["Impact Details"] == "minor"


def test_deviation_equipment_id_and_number_share_one_source_column():
    fields = build_trackwise_fields(
        row(title="t", investigator="inv", rci_number="r1", instrument_equipment_id="EQ-9"),
        "Deviation",
        extended=True,
    )
    assert fields["Equipment ID"] == "EQ-9"
    assert fields["Equipment Number"] == "EQ-9"


def test_oos_uses_failure_type_directly():
    fields = build_trackwise_fields(
        row(title="t", investigator="inv", rci_number="r1", failure_type="Assay"),
        "Out Of Specification",
    )
    assert fields["Failure type"] == "Assay"


def test_oot_merges_root_cause_category_narrowest_to_broadest():
    fields = build_trackwise_fields(
        row(
            title="t",
            investigator="inv",
            rci_number="r1",
            root_cause_sub_category="Sub",
            root_cause_category="Category",
            root_cause_broad_category="Broad",
        ),
        "Out of Trend",
    )
    assert fields["Failure type"] == "Sub, Category, Broad"


def test_oot_merge_skips_blank_parts():
    fields = build_trackwise_fields(
        row(title="t", investigator="inv", rci_number="r1", root_cause_category="Category"),
        "Out of Trend",
    )
    assert fields["Failure type"] == "Category"


def test_oot_merge_returns_none_when_all_parts_blank():
    fields = build_trackwise_fields(
        row(title="t", investigator="inv", rci_number="r1"),
        "Out of Trend",
    )
    assert fields["Failure type"] is None


def test_market_complaint_basic_and_extended():
    fields = build_trackwise_fields(
        row(
            title="t",
            investigator="inv",
            rci_number="r1",
            date_complaint_received="2026-01-01",
            complaint_reported_by="J Doe",
            name_of_material="Paracetamol",
            complainant_name="Acme Pharmacy",
            complaint_number="C-1",
        ),
        "Complaint",
        extended=True,
    )
    assert fields["Products Information"] == "Paracetamol"
    assert fields["Complainant Name"] == "Acme Pharmacy"
    assert fields["Complaint Number"] == "C-1"


def test_unknown_qe_type_returns_empty_dict_without_universal_fields():
    fields = build_trackwise_fields(row(investigator="inv", rci_number="r1"), "Something Else")
    assert fields == {}


def test_investigation_type_set_manufacturing_when_is_mfg_rci_true():
    fields = build_trackwise_fields(
        row(title="t", investigator="inv", rci_number="r1", is_mfg_rci=True),
        "Out Of Specification",
    )
    assert fields["investigation_type"] == "Manufacturing"


def test_investigation_type_set_qc_when_is_mfg_rci_false():
    fields = build_trackwise_fields(
        row(title="t", investigator="inv", rci_number="r1", is_mfg_rci=False),
        "Out Of Specification",
    )
    assert fields["investigation_type"] == "QC"


def test_investigation_type_omitted_when_is_mfg_rci_not_backfilled():
    fields = build_trackwise_fields(
        row(title="t", investigator="inv", rci_number="r1"),
        "Out Of Specification",
    )
    assert "investigation_type" not in fields


def test_resolved_event_type():
    assert resolved_event_type("Out Of Specification") == "OOS"
    assert resolved_event_type("Complaint") == "Market Complaint"
    assert resolved_event_type(None) is None
    assert resolved_event_type("Unknown") is None


def test_normalize_rci_id():
    assert normalize_rci_id("none") is None
    assert normalize_rci_id("") is None
    assert normalize_rci_id("504544") == "504544"
