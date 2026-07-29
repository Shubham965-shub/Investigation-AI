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
- Deviation-extended's "Equipment ID": equipment_number was confirmed
  [DROPPED] from dim_event in the 2026-07-24 schema update, with no
  replacement column added — reuses dim_equipment.instrument_equipment_id
  (same real column "Instrument ID Number" already uses; 95.3% filled for
  Deviation as of 2026-07-28) rather than being hardcoded None, per the same
  "no second source column" precedent as Equipment Name above. [2026-07-28:
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
from typing import Any, Dict, Optional

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


def build_trackwise_fields(row: asyncpg.Record, qe_type: str, extended: bool = False) -> Dict[str, Any]:
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
                    "Related Market": _val(row, "related_market"),
                    "Related Customer": _val(row, "related_customer"),
                    "Equipment ID": _val(row, "instrument_equipment_id"),  # equipment_number [DROPPED] 2026-07-24; reuses the same column "Instrument ID Number" uses
                    "Deviation Owner": _val(row, "owner_name"),
                    "Originator": _val(row, "originator"),
                    "Immediate Actions": _val(row, "immediate_actions"),
                    "Impact on Deviation Batches": _val(row, "impact_on_deviation_batches"),
                    "Impact Details": _val(row, "impact_details"),
                    "Immediate Cause Known": _val(row, "immediate_cause_known"),
                    "Cause Detail": _val(row, "cause_detail"),
                    "Proposal for Resolution": _val(row, "proposal_for_resolution"),
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
            "Failure type": _val(row, "failure_type"),
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
