"""Read queries against the STAR schema (star_schema.sql)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import asyncpg

from backend.clients.db_client import get_pool

_INVESTIGATION_ROW_QUERY = """
-- dim_event.status was renamed to dim_event.module on 2026-07-27 (see project
-- memory: star_schema) — aliased back to `status` here since that's the key
-- the 4 module routers/module_stage.stage_for() already expect.
SELECT
    f.deviation_id,
    ec.qe_type,
    e.module AS status,
    e.failure_type,
    -- OOT's failure_type is 0% filled live (2026-07-31) — these 3 are what
    -- OOT's "Failure Type" trackwise field is actually built from instead
    -- (see field_mapping.py's _merge_root_cause_category).
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
    f.due_date
FROM fact_qms_event f
JOIN dim_event e ON e.deviation_id = f.deviation_id
LEFT JOIN dim_event_classification ec ON ec.event_classification_key = f.event_classification_key
LEFT JOIN dim_product p ON p.product_key = f.product_key
LEFT JOIN dim_equipment eq ON eq.equipment_key = f.equipment_key
LEFT JOIN dim_batch b ON b.batch_key = f.batch_key
LEFT JOIN dim_investigator di ON di.investigator_key = f.investigator_key
LEFT JOIN dim_rci r ON r.rci_key = f.rci_key
WHERE f.deviation_id = $1
LIMIT 1
"""


async def fetch_investigation_row(deviation_id: int) -> Optional[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(_INVESTIGATION_ROW_QUERY, deviation_id)


# Reuses the same open/closed/cancelled classification action_center_queries.py
# established (module='Cancelled' -> Cancelled; closed_on set -> Closed;
# else -> Open) — bool_or across GROUP BY handles deviation_ids with more
# than one fact_qms_event row (a known, legitimate source-pipeline pattern).
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
    """Open/Closed/Cancelled classification for a batch of deviation_ids —
    used by the "View Historic Data" panel to annotate results returned by
    ds's /api/search (which only knows about its own search corpus, not
    Trackwise's own status fields)."""
    if not deviation_ids:
        return {}
    pool = get_pool()
    async with pool.acquire() as conn:
        status_rows = await conn.fetch(_INVESTIGATION_STATUS_QUERY, deviation_ids)
        return {r["deviation_id"]: r["status"] for r in status_rows}


# Only investigators currently assigned to an OPEN investigation (2026-08-19,
# per the user, re-scoping the prior 2026-08-13 "every investigator who has
# ever appeared, open or closed or cancelled" decision back down) — used to
# populate RCI Plan Creation's task-assignee dropdown, which shouldn't offer
# someone no longer actively working anything. `f.closed_on IS NULL` is the
# authoritative "open" filter (same one action_center_queries.py's
# _OPEN_INVESTIGATIONS_QUERY uses) — dim_event.open_investigation_status is a
# different, severity/bucket field, not this. Joined through fact_qms_event
# (not a bare SELECT DISTINCT investigator FROM dim_investigator) so this
# only ever returns investigators actually referenced by a real investigation,
# not any unused/orphaned dim_investigator row.
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
