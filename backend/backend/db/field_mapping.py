"""Maps a joined STAR-schema row to the trackwise_fields keys frontend and
InvestigationAi_DS both expect (confirmed identical between the two).

Known gaps (best-effort, flagged for the DB owner, not silently guessed):
- OOS/OOT "Batches Details" has no clear source column; omitted.
- "Equipment Name"/"Name of the Instrument" both resolve to instrument_equipment
  (no second source column exists).
- Deviation-extended "Equipment ID" and "Equipment Number" both reuse
  instrument_equipment_id — equipment_number was dropped from dim_event with
  no replacement column.
- Market Complaint "Products Information" uses dim_product.name_of_material —
  products_information_product_name was dropped from the schema.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

import asyncpg

QE_TYPE_TO_EVENT_TYPE: Dict[str, str] = {
    "Deviation": "Deviation",
    "Out Of Specification": "OOS",
    "Out of Trend": "OOT",
    "Complaint": "Market Complaint",
}


def _val(row: asyncpg.Record, col: str) -> Any:
    v = row.get(col)
    if isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
        return v.isoformat()
    return v


def _date_only(row: asyncpg.Record, col: str) -> Any:
    """Like _val, but drops any time component — date_opened is a TIMESTAMP
    column but its trackwise field is date-only; _val() alone would leak a
    full datetime into the RCI Report's "Date of Initiation" field."""
    v = row.get(col)
    if isinstance(v, datetime.datetime):
        return v.date().isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    return v


def _val_joined(row: asyncpg.Record, col: str, sep: str = ", ") -> Any:
    """Like _val, but joins array-typed columns into a single string.
    related_market/related_customer are text[] in dim_event, but DS's
    ExtendedDeviationTrackwiseFields declares both as plain str fields — the
    RCI-plan UI field is a plain text input, so joined here rather than
    loosening DS's schema."""
    v = _val(row, col)
    if isinstance(v, list):
        return sep.join(str(item) for item in v)
    return v


def _merge_root_cause_category(row: asyncpg.Record) -> Optional[str]:
    """OOT's failure_type column is ~0% filled live; root_cause_sub/category/
    broad_category are ~96% filled instead and are what OOT's "Failure Type"
    field should reflect. OOS is the opposite (failure_type filled,
    root_cause_broad_category isn't), so this merge is OOT-only. Joined
    narrowest-to-broadest, blank parts skipped."""
    parts = [
        _val(row, "root_cause_sub_category"),
        _val(row, "root_cause_category"),
        _val(row, "root_cause_broad_category"),
    ]
    joined = ", ".join(str(p) for p in parts if p)
    return joined or None


def _as_string_list(row: asyncpg.Record, col: str) -> List[str]:
    """Like _val, but for a text[] column consumed as a list — the inverse
    of _val_joined."""
    v = _val(row, col)
    if isinstance(v, list):
        return [str(item) for item in v]
    return [str(v)] if v else []


def _val_as_list(row: asyncpg.Record, col: str) -> List[str]:
    """Wraps a plain-text column into the single-element list
    ExtendedDeviationTrackwiseFields's list-typed fields expect.
    NOTE: impact_on_other_batches/impact_justification were suggested as an
    alternate source for "Impact Details" but are 0% filled for Deviation
    (only populated for OOS/OOT/Complaint, which have no such field) —
    impact_details (94.5% filled for Deviation) is kept as the real source,
    just wrapped in a list."""
    v = _val(row, col)
    return [str(v)] if v else []


def build_trackwise_fields(
    row: asyncpg.Record, qe_type: str, extended: bool = False, for_rci_report: bool = False
) -> Dict[str, Any]:
    fields = _type_specific_trackwise_fields(row, qe_type, extended=extended, for_rci_report=for_rci_report)
    # Universal across event types: rci_key is the genuine Trackwise RCI ID —
    # distinct from dim_rci.reference_number, which is just deviation_id as
    # a string and was wrongly used here previously.
    if fields:
        fields["Investigator"] = _val(row, "investigator")
        fields["RCI Number"] = _val(row, "rci_number")
    return fields


def _type_specific_trackwise_fields(
    row: asyncpg.Record, qe_type: str, extended: bool = False, for_rci_report: bool = False
) -> Dict[str, Any]:
    event_type = QE_TYPE_TO_EVENT_TYPE.get(qe_type)

    if event_type == "Deviation":
        fields: Dict[str, Any] = {
            "title": _val(row, "title"),
            "Observed By": _val(row, "observed_by"),
            "Batch Number / AR Number": _val(row, "batch_no"),
            "Product / Material Code": _val(row, "sfg_code"),
            "Product Name / Material Name": _val(row, "name_of_material"),
            "Deviation To": _val(row, "deviation_to"),
            "Department": _val(row, "department"),
            "Equipment Name": _val(row, "instrument_equipment"),
            "Instrument ID Number": _val(row, "instrument_equipment_id"),
            "Name of the Instrument": _val(row, "instrument_equipment"),
            "description": _val(row, "description"),
        }
        if extended:
            fields.update(
                {
                    "Deviation Number": _val(row, "deviation_number"),
                    "Date Opened": _date_only(row, "date_opened"),
                    "Observation Date": _val(row, "observation_date"),
                    "Observation Time": _val(row, "observation_time"),
                    "Failure Duration": _val(row, "failure_duration"),
                    # RciReportDeviationTrackwiseFields wants the opposite shape from
                    # ExtendedDeviationTrackwiseFields for these four fields (see ds
                    # schemas.py) — raw column shape for rci_report, joined/wrapped
                    # shape for RCI Plan otherwise.
                    "Related Market": (
                        _as_string_list(row, "related_market") if for_rci_report else _val_joined(row, "related_market")
                    ),
                    "Related Customer": (
                        _as_string_list(row, "related_customer") if for_rci_report else _val_joined(row, "related_customer")
                    ),
                    "Equipment ID": _val(row, "instrument_equipment_id"),  # equipment_number was dropped; reuses instrument_equipment_id
                    "Equipment Number": _val(row, "instrument_equipment_id"),  # no separate column exists; same source as Equipment ID
                    "Deviation Owner": _val(row, "owner_name"),
                    "Originator": _val(row, "originator"),
                    "Immediate Actions": _val(row, "immediate_actions") if for_rci_report else _val_as_list(row, "immediate_actions"),
                    "Impact on Deviation Batches": _val(row, "impact_on_deviation_batches"),
                    "Impact Details": _val(row, "impact_details") if for_rci_report else _val_as_list(row, "impact_details"),
                    "Immediate Cause Known": _val(row, "immediate_cause_known"),
                    "Cause Detail": _val(row, "cause_detail"),
                    "Proposal for Resolution": _val_as_list(row, "proposal_for_resolution"),
                    # Only declared on RciReportDeviationTrackwiseFields; without it
                    # the Correction & Remedial Action section stayed empty. Harmless
                    # elsewhere since unknown dict keys are ignored.
                    "Correction or Remedial Action": _val(row, "correction_or_remedial_action"),
                }
            )
        return fields

    if event_type in ("OOS", "OOT"):
        return {
            "title": _val(row, "title"),
            "description": _val(row, "description"),
            "observation_date": _val(row, "observation_date"),
            "Laboratory Details": _val(row, "laboratory_details"),
            "Specification Number": _val(row, "specification_number"),
            "Stability Condition": _val(row, "stability_condition"),
            "Stability Protocol Number": _val(row, "stability_protocol_number"),
            "Labelled Storage Conditions": _val(row, "labelled_storage_conditions"),
            "Failure type": _merge_root_cause_category(row) if event_type == "OOT" else _val(row, "failure_type"),
            "Observation Time": _val(row, "observation_time"),
            "Product Type": _val(row, "product_type"),
            "STP Number": _val(row, "stp_number"),
            "Stability Time Point": _val(row, "stability_time_point"),
            "Analyst Name": _val(row, "analyst_name"),
            "Batch Number / AR Number": _val(row, "batch_no"),
            "Product Name / Material Name": _val(row, "name_of_material"),
            "Instrument ID Number": _val(row, "instrument_equipment_id"),
            "Product / Material Code": _val(row, "sfg_code"),
            "Name of the Instrument": _val(row, "instrument_equipment"),
            "Name of the Test": _val(row, "name_of_test"),
            "Sample Number": _val(row, "sample_number"),
        }

    if event_type == "Market Complaint":
        fields = {
            "title": _val(row, "title"),
            "Date Complaint Received": _val(row, "date_complaint_received"),
            "Market Complaint Reported By": _val(row, "complaint_reported_by"),
            "Reference Complaint Number": _val(row, "reference_complaint_number"),
            "description": _val(row, "description"),
            "Products Information": _val(row, "name_of_material"),  # products_information_product_name was dropped; name_of_material used instead
            "Dosage Form": _val(row, "dosage_form"),
            "Market": _val(row, "market"),
            "Product Manufacturing Info": _val(row, "product_manufacturing_info"),
        }
        if extended:
            fields.update(
                {
                    "Complainant Name": _val(row, "complainant_name"),
                    "Complaint Received By": _val(row, "complaint_received_by"),
                    "Customer": _val(row, "customer"),
                    "Complaint Country": _val(row, "complainant_country"),
                    "Complaint Number": _val(row, "complaint_number"),
                }
            )
        return fields

    return {}


def resolved_event_type(qe_type: Optional[str]) -> Optional[str]:
    if qe_type is None:
        return None
    return QE_TYPE_TO_EVENT_TYPE.get(qe_type)


def normalize_rci_id(raw: str) -> Optional[str]:
    """Normalizes a router path segment into the value passed to query
    functions: the literal segment "none" (or an empty string) means "no RCI"
    and must become real SQL NULL, never the string "none"."""
    return None if raw in ("", "none") else raw
