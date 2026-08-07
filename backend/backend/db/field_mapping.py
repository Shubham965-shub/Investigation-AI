"""Maps a joined STAR-schema row to the exact trackwise_fields keys the
frontend (constants/trackwiseFields.ts) and InvestigationAi_DS
(agents/shared/schemas.py, agents/problem_statement_evaluation/v2/schemas.py)
both expect — confirmed identical between the two, no renaming layer between
frontend and DS.

Known gaps (best-effort, not silently guessed — flag for the DB owner):
- OOS/OOT's "Batches Details" has no clear source column; omitted. NOTE: the
  2026-07-24 dim_event expansion added two candidate array pairs
  (affected_batches_batch_ar_number/_product_material_name and
  batches_details_batch_no_ar_no/_product_or_material_name) that look
  related to this concept — not wired up here yet since it's unconfirmed
  which (if either) maps to "Batches Details" vs. some other UI field.
- "Equipment Name" and "Name of the Instrument" both resolve to the single
  instrument_equipment column — there's no second source column for either.
- Deviation-extended's "Equipment ID" AND "Equipment Number" (two separate
  required fields in DS's ExtendedDeviationTrackwiseFields): equipment_number
  was confirmed [DROPPED] from dim_event in the 2026-07-24 schema update, with
  no replacement column added — both reuse dim_equipment.instrument_equipment_id
  (same real column "Instrument ID Number" already uses; 95.3% filled for
  Deviation as of 2026-07-28) rather than being hardcoded None, per the same
  "no second source column" precedent as Equipment Name above. [2026-07-29:
  "Equipment Number" was previously missing from this dict entirely (not
  hardcoded None — just absent), which made every single Deviation RCI-plan
  generation call fail DS's validation with "missing required fields:
  Equipment Number" — confirmed by the backend engineer that
  instrument_equipment_id is the right source for it too.] [2026-07-28:
  previously hardcoded None here regardless of live data — changed after the
  user flagged that nothing should be null-by-code when a real column value
  might exist; None should only ever come from a genuinely blank DB value.]
- Market Complaint's "Products Information": products_information_product_name
  is confirmed [DROPPED] from the real schema (see star_schema.sql), but
  dim_product.name_of_material (joined via fact_qms_event.product_key) is
  populated for 100% of live Complaint rows (692/692 as of 2026-07-28) — same
  column OOS/OOT's "Product Name / Material Name" already uses. Wired to that
  instead of a hardcoded None. [2026-07-28: this was the field silently
  guaranteeing every single Market Complaint evidence-collection call failed
  DS's validation — see project memory: rci_plan_schema_gap / star_schema.]
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


def _val_joined(row: asyncpg.Record, col: str, sep: str = ", ") -> Any:
    """Like _val, but joins array-typed columns into a single string.

    related_market/related_customer are text[] in dim_event (confirmed via
    information_schema, 2026-07-29) for every row regardless of event type,
    but ExtendedDeviationTrackwiseFields (DS, used for RCI plan generation)
    declares both as plain required str fields — every Deviation RCI-plan
    request failed DS's validation as a result (missing-type error, not a
    null/empty one). Joining here rather than loosening DS's schema, since a
    single flat string is what the RCI-plan UI field (a plain text input,
    not a "list"-kind one — see frontend constants/trackwiseFields.ts) is
    designed to display and round-trip.
    """
    v = _val(row, col)
    if isinstance(v, list):
        return sep.join(str(item) for item in v)
    return v


def _merge_root_cause_category(row: asyncpg.Record) -> Optional[str]:
    """OOT's failure_type column is 0% filled live (2398/2398 null as of
    2026-07-31) — root_cause_sub_category/root_cause_category/
    root_cause_broad_category are ~96% filled instead (2308/2398) and are
    what OOT's "Failure Type" trackwise field should actually reflect, per
    the user. OOS is the opposite (failure_type is 98.8% filled,
    root_cause_broad_category is 0% filled for OOS specifically) so this is
    OOT-only — see build_trackwise_fields. Joined narrowest-to-broadest per
    the user; blank parts are skipped rather than leaving stray separators.
    """
    parts = [
        _val(row, "root_cause_sub_category"),
        _val(row, "root_cause_category"),
        _val(row, "root_cause_broad_category"),
    ]
    joined = ", ".join(str(p) for p in parts if p)
    return joined or None


def _val_as_list(row: asyncpg.Record, col: str) -> List[str]:
    """Wraps a plain-text column into the single-element list
    ExtendedDeviationTrackwiseFields's list-typed fields expect.

    NOTE on impact_on_other_batches/impact_justification: the backend
    engineer suggested merging these into "Impact Details" instead of
    impact_details (2026-07-29), but a per-event-type breakdown showed
    both are 0/2304 filled for qe_type='Deviation' specifically — they're
    only ever populated for OOS/OOT/Complaint rows, none of which have an
    "Impact Details" field at all (Deviation-only, extended schema). The
    impact_details column itself is 2177/2304 (94.5%) filled for Deviation,
    so it's kept as the source here; only wrapped in a list to satisfy the
    schema's type, not replaced. Flagged back rather than merged in blind.
    """
    v = _val(row, col)
    return [str(v)] if v else []


def build_trackwise_fields(row: asyncpg.Record, qe_type: str, extended: bool = False) -> Dict[str, Any]:
    fields = _type_specific_trackwise_fields(row, qe_type, extended=extended)
    # Universal, regardless of event type (2026-08-07, per the user) —
    # dim_investigator.investigator via fact_qms_event.investigator_key, and
    # dim_rci.reference_number via fact_qms_event.rci_key. Neither was
    # previously joined into fetch_investigation_row's query at all, so
    # rci_plan_export.py had no real source for either and left them blank/
    # fell back to the differently-scoped "Deviation Owner" (dim_event.owner_name).
    if fields:
        fields["Investigator"] = _val(row, "investigator")
        fields["RCI Number"] = _val(row, "rci_number")
    return fields


def _type_specific_trackwise_fields(row: asyncpg.Record, qe_type: str, extended: bool = False) -> Dict[str, Any]:
    event_type = QE_TYPE_TO_EVENT_TYPE.get(qe_type)

    if event_type == "Deviation":
        fields: Dict[str, Any] = {
            "title": _val(row, "title"),
            "Observed By": _val(row, "observed_by"),
            "Batch Number / AR Number": _val(row, "batch_no"),
            "Product / Material Code": _val(row, "sfg_code"),
            "Product Name / Material Name": _val(row, "name_of_material"),
            "Deviation To": _val(row, "deviation_to"),
            "Equipment Name": _val(row, "instrument_equipment"),
            "Instrument ID Number": _val(row, "instrument_equipment_id"),
            "Name of the Instrument": _val(row, "instrument_equipment"),
            "description": _val(row, "description"),
        }
        if extended:
            fields.update(
                {
                    "Deviation Number": _val(row, "deviation_number"),
                    "Date Opened": _val(row, "date_opened"),
                    "Observation Date": _val(row, "observation_date"),
                    "Observation Time": _val(row, "observation_time"),
                    "Failure Duration": _val(row, "failure_duration"),
                    "Related Market": _val_joined(row, "related_market"),
                    "Related Customer": _val_joined(row, "related_customer"),
                    "Equipment ID": _val(row, "instrument_equipment_id"),  # equipment_number [DROPPED] 2026-07-24; reuses the same column "Instrument ID Number" uses
                    "Equipment Number": _val(row, "instrument_equipment_id"),  # per backend engineer (2026-07-29): same source column as Equipment ID/Instrument ID Number, no separate column exists
                    "Deviation Owner": _val(row, "owner_name"),
                    "Originator": _val(row, "originator"),
                    "Immediate Actions": _val_as_list(row, "immediate_actions"),
                    "Impact on Deviation Batches": _val(row, "impact_on_deviation_batches"),
                    "Impact Details": _val_as_list(row, "impact_details"),
                    "Immediate Cause Known": _val(row, "immediate_cause_known"),
                    "Cause Detail": _val(row, "cause_detail"),
                    "Proposal for Resolution": _val_as_list(row, "proposal_for_resolution"),
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
            "Products Information": _val(row, "name_of_material"),  # products_information_product_name [DROPPED]; name_of_material is 100% filled for live Complaint rows
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
