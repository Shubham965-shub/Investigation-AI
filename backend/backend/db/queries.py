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


# t_deviations_vector_test is ds's search corpus (pgvector embeddings over
# historical investigations, including this one if it's been synced there) —
# not part of star_schema.sql, but the same physical Postgres instance, so a
# plain query works without going through ds's HTTP API. Doing the nearest-
# neighbor lookup entirely in SQL (subquery for the target row's own vector)
# avoids needing a Python pgvector codec or a fresh embedding call — the
# current investigation's own description_vector is reused directly.
_SIMILAR_INVESTIGATIONS_QUERY = """
WITH target AS (
    SELECT description_vector::vector AS description_vector
    FROM t_deviations_vector_test
    WHERE deviation_id = $1 AND description_vector IS NOT NULL
)
SELECT
    v.deviation_id,
    v.title,
    (1 - (v.description_vector::vector <=> target.description_vector)) AS relevance_score
FROM t_deviations_vector_test v, target
WHERE v.deviation_id != $1
  AND v.description_vector IS NOT NULL
  -- ~16% of rows have an all-zero placeholder embedding, not a real one —
  -- cosine distance against a zero vector is undefined (NaN), and Postgres
  -- sorts NaN as larger than any real number in DESC order, so without this
  -- filter every zero-vector row floats to the very top and buries the
  -- genuine matches entirely (confirmed live, 2026-07-30).
  AND vector_norm(v.description_vector::vector) > 0
ORDER BY relevance_score DESC
LIMIT $2
"""

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


async def fetch_similar_investigations(deviation_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    """Historic investigations this one is most similar to, per pgvector
    cosine similarity on t_deviations_vector_test.description_vector.

    Returns [] if the investigation itself has no row/vector there yet
    (e.g. not synced) rather than raising — this is a "nice to have" panel,
    not a hard dependency for the Problem Statement page.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        matches = await conn.fetch(_SIMILAR_INVESTIGATIONS_QUERY, deviation_id, limit)
        if not matches:
            return []

        ids = [m["deviation_id"] for m in matches]
        status_rows = await conn.fetch(_INVESTIGATION_STATUS_QUERY, ids)
        status_by_id = {r["deviation_id"]: r["status"] for r in status_rows}

        return [
            {
                "deviation_id": m["deviation_id"],
                "title": m["title"],
                "status": status_by_id.get(m["deviation_id"], "Unknown"),
                "relevance_score": round(float(m["relevance_score"]), 4),
            }
            for m in matches
        ]
