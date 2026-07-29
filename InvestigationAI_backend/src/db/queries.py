"""Read queries against the STAR schema (star_schema.sql)."""
from __future__ import annotations

from typing import Optional

import asyncpg

from src.clients.db_client import get_pool

_INVESTIGATION_ROW_QUERY = """
-- dim_event.status was renamed to dim_event.module on 2026-07-27 (see project
-- memory: star_schema) — aliased back to `status` here since that's the key
-- the 4 module routers/module_stage.stage_for() already expect.
SELECT
    f.deviation_id,
    ec.qe_type,
    e.module AS status,
    e.failure_type,
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
    eq.instrument_equipment_id
FROM fact_qms_event f
JOIN dim_event e ON e.deviation_id = f.deviation_id
LEFT JOIN dim_event_classification ec ON ec.event_classification_key = f.event_classification_key
LEFT JOIN dim_product p ON p.product_key = f.product_key
LEFT JOIN dim_equipment eq ON eq.equipment_key = f.equipment_key
LEFT JOIN dim_batch b ON b.batch_key = f.batch_key
WHERE f.deviation_id = $1
LIMIT 1
"""


async def fetch_investigation_row(deviation_id: int) -> Optional[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(_INVESTIGATION_ROW_QUERY, deviation_id)
