"""Queries backing the Analytics dashboard (GET /api/analytics/summary).

Scope, first real-data pass (2026-08-03) — per the user, only the sections
that map cleanly onto real columns are wired this pass: Event, CAPA
with/without, Root Cause presence, and Failure Pattern (product/equipment
frequency). Investigation Quality (IQ Score) and the CAPA L1-L5 hierarchy
ranking have no backing column anywhere in the star schema (verified against
the live DB) and are NOT computed here — the frontend keeps showing mock data
for those, clearly commented, until a real formula/mapping is defined.

Unlike action_center_queries.py (which scopes to ~170 open investigations),
this covers the full event population (6,686 distinct deviation_ids as of
2026-08-03) — still small enough to pull as one flat, deduped row set and
aggregate in Python, matching this repo's existing convention rather than
hand-rolling multi-CTE SQL.
"""
from __future__ import annotations

from typing import List

import asyncpg

from backend.clients.db_client import get_pool

# Same known duplication as action_center_queries.py's _OPEN_INVESTIGATIONS_QUERY
# (274 deviation_ids have more than one fact_qms_event row) — DISTINCT ON
# picks the most recently updated snapshot per deviation_id so counts here
# reflect real investigations, not fact-table rows.
_ANALYTICS_ROWS_QUERY = """
SELECT deviation_id, date_opened, due_date, capa_record_id, qe_type,
       open_investigation_status, root_cause_category, root_cause_broad_category,
       root_cause_sub_category, product, equipment, site, department
FROM (
    SELECT DISTINCT ON (f.deviation_id)
        f.deviation_id,
        f.date_opened,
        f.due_date,
        f.capa_record_id,
        ec.qe_type,
        e.open_investigation_status,
        e.root_cause_category,
        e.root_cause_broad_category,
        e.root_cause_sub_category,
        p.name_of_material AS product,
        eq.instrument_equipment AS equipment,
        loc.location AS site,
        dept.department,
        f.pg_updated_at_timestamp
    FROM fact_qms_event f
    JOIN dim_event e ON e.deviation_id = f.deviation_id
    LEFT JOIN dim_event_classification ec ON ec.event_classification_key = f.event_classification_key
    LEFT JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN dim_equipment eq ON eq.equipment_key = f.equipment_key
    LEFT JOIN dim_location loc ON loc.location_key = f.location_key
    LEFT JOIN dim_department dept ON dept.department_key = f.department_key
    ORDER BY f.deviation_id, f.pg_updated_at_timestamp DESC NULLS LAST
) dedup
"""


async def fetch_analytics_rows() -> List[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(_ANALYTICS_ROWS_QUERY)