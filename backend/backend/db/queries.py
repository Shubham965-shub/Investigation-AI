"""Read queries against the STAR schema (star_schema.sql)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import asyncpg

from backend.clients.db_client import get_pool

_INVESTIGATION_ROW_BASE_QUERY = """
-- dim_event.status was renamed to dim_event.module; aliased back to `status`
-- here since that's the key module_stage.stage_for() expects.
SELECT
    f.deviation_id,
    ec.qe_type,
    e.module AS status,
    e.failure_type,
    -- OOT's failure_type is ~0% filled; these 3 build OOT's "Failure Type"
    -- field instead (see field_mapping._merge_root_cause_category).
    e.root_cause_broad_category,
    e.root_cause_category,
    e.root_cause_sub_category,
    e.title,
    e.description,
    e.deviation_to,
    e.deviation_number,
    f.date_opened,
    e.observation_date,
    e.observation_time,
    e.failure_duration,
    e.immediate_cause_known,
    e.cause_detail,
    e.immediate_actions,
    e.impact_on_deviation_batches,
    e.impact_details,
    e.proposal_for_resolution,
    e.correction_or_remedial_action,
    e.market,
    e.related_market,
    e.laboratory_details,
    e.name_of_test,
    e.sample_number,
    e.specification_number,
    e.stability_condition,
    e.stability_protocol_number,
    e.stability_time_point,
    e.stp_number,
    e.labelled_storage_conditions,
    e.complaint_number,
    e.complainant_name,
    e.complainant_country,
    e.complaint_received_by,
    e.complaint_reported_by,
    e.customer,
    e.date_complaint_received,
    e.reference_complaint_number,
    e.sfg_code,
    e.product_type,
    e.dosage_form,
    e.product_manufacturing_info,
    b.batch_no,
    e.related_customer,
    e.originator,
    e.analyst_name,
    e.owner_name,
    e.observed_by,
    p.name_of_material,
    eq.instrument_equipment,
    eq.instrument_equipment_id,
    di.investigator,
    r.rci_key AS rci_number,
    d.department,
    f.due_date,
    e.criticality,
    -- Distinct from dim_event_classification (`ec` below, an unrelated
    -- qe_type lookup). Critical/Major/Minor for Deviation/Complaint only;
    -- NULL for OOS/OOT or an unclassified record.
    e.event_classification
FROM fact_qms_event f
JOIN dim_event e ON e.deviation_id = f.deviation_id
LEFT JOIN dim_event_classification ec ON ec.event_classification_key = f.event_classification_key
LEFT JOIN dim_product p ON p.product_key = f.product_key
LEFT JOIN dim_equipment eq ON eq.equipment_key = f.equipment_key
LEFT JOIN dim_batch b ON b.batch_key = f.batch_key
LEFT JOIN dim_investigator di ON di.investigator_key = f.investigator_key
LEFT JOIN dim_rci r ON r.rci_key = f.rci_key
LEFT JOIN dim_department d ON d.department_key = f.department_key
"""


async def fetch_investigation_row(deviation_id: int, rci_id: Optional[str] = None) -> Optional[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        if rci_id is not None:
            try:
                rci_key = int(rci_id)
            except ValueError:
                rci_key = None
            if rci_key is not None:
                row = await conn.fetchrow(
                    _INVESTIGATION_ROW_BASE_QUERY + "WHERE f.deviation_id = $1 AND f.rci_key = $2 LIMIT 1",
                    deviation_id, rci_key,
                )
                if row is not None:
                    return row
        # No rci_id given, or it didn't match any row for this deviation (defensive,
        # shouldn't happen in practice) — preserves today's exact arbitrary-row behavior.
        return await conn.fetchrow(_INVESTIGATION_ROW_BASE_QUERY + "WHERE f.deviation_id = $1 LIMIT 1", deviation_id)


# Same open/closed/cancelled classification as action_center_queries.py;
# bool_or handles deviation_ids with more than one fact_qms_event row.
_INVESTIGATION_STATUS_QUERY = """
SELECT
    f.deviation_id,
    CASE
        WHEN bool_or(e.module = 'Cancelled') THEN 'Cancelled'
        WHEN bool_or(f.closed_on IS NOT NULL) THEN 'Closed'
        ELSE 'Open'
    END AS status
FROM fact_qms_event f
JOIN dim_event e ON e.deviation_id = f.deviation_id
WHERE f.deviation_id = ANY($1::int[])
GROUP BY f.deviation_id
"""


async def fetch_investigation_statuses(deviation_ids: List[int]) -> Dict[int, str]:
    """Open/Closed/Cancelled per deviation_id — used to annotate ds's
    /api/search results with Trackwise's own status fields."""
    if not deviation_ids:
        return {}
    pool = get_pool()
    async with pool.acquire() as conn:
        status_rows = await conn.fetch(_INVESTIGATION_STATUS_QUERY, deviation_ids)
        return {r["deviation_id"]: r["status"] for r in status_rows}


# Only investigators on a currently open investigation (closed_on IS NULL,
# not the unrelated open_investigation_status field) — populates RCI Plan's
# assignee dropdown. Joined through fact_qms_event so this returns only
# investigators actually referenced, not orphaned dim_investigator rows.
_OPEN_INVESTIGATORS_QUERY = """
SELECT DISTINCT di.investigator
FROM fact_qms_event f
JOIN dim_investigator di ON di.investigator_key = f.investigator_key
WHERE di.investigator IS NOT NULL AND f.closed_on IS NULL
ORDER BY di.investigator
"""


async def fetch_open_investigators() -> List[str]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_OPEN_INVESTIGATORS_QUERY)
        return [r["investigator"] for r in rows]
