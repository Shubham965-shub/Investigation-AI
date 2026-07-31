"""Queries backing the Action Center dashboard.

Scope: everything here describes OPEN investigations only (closed_on IS
NULL — 450/11,820 as of 2026-07-27) — matches the dashboard's own "Status Of
Open Investigations" section, and keeps result sets small enough to
aggregate in a single query. closed_on is the authoritative close date;
date_closed is a separate field that can be set on rows that are still
genuinely open (207 confirmed live) and must not be used for this filter.

Business rules, per the backend (data) engineer (2026-07-28) unless noted
otherwise — see project memory (action_center_roles, module_progress_grouping,
star_schema):

- PROGRESS CHART: bucketed by dim_event.module (Trackwise's own current-stage
  field, renamed from `status` on 2026-07-27 — was previously undocumented/
  near-constant-looking, now confirmed to carry real per-row stage text),
  mapped to module_stage-style labels. `module = 'Cancelled'` rows are
  excluded from the chart entirely (see action_center.py). The per-bar
  on_track/at_risk/delayed stacking comes from dim_event.module_risk_status.
- STATUS CARDS (4-card + 6-card severity view): bucketed directly from
  dim_event.open_investigation_status (On Track/At Risk/Overdue/Unassigned),
  not the day-threshold heuristic previously used as a placeholder — see
  action_center.py's _bucket_for.
- STAGE (X/6 steps progress bar per investigation row) [UPDATED 2026-07-28]:
  now driven by module_stage.stage_for(dim_event.module) — the same "state
  change detection" mapping the 4 individual module pages already used —
  NOT fetch_module_completion()'s generated-content-table row count anymore.
  Per the user: dim_event.module is for the progress chart's bucketing
  (above) AND this per-row stage; fetch_module_completion() is no longer
  called from action_center.py at all (the function itself still exists in
  this file, just unused here — kept in case it's needed again).
- PENDING ACTIONS: unassigned or overdue cases; the description is "the
  task to be done after the current one" (user's own phrasing) — i.e. the
  next module label following the investigation's current stage (same STAGE
  value above, so also module-state-based as of 2026-07-28).
"""
from __future__ import annotations

from typing import Dict, List

import asyncpg

from backend.clients.db_client import get_pool

# Order matches the first 4 entries of module_stage.MODULE_LABELS. Task
# Critique/RCI Report have no backing tables yet (see project memory:
# module_progress_grouping) and are intentionally excluded.
_MODULE_COMPLETION_TABLES: List[str] = [
    "investigation_problem_statements",
    "investigation_evidence_items",
    "investigation_questionnaire_items",
    "investigation_rci_sections",
]

QE_TYPE_TO_STAT_LABEL: Dict[str, str] = {
    "Deviation": "Deviation",
    "Out Of Specification": "OOS",
    "Out of Trend": "OOT",
    "Complaint": "Market Complaint",
}

_OPEN_INVESTIGATIONS_QUERY = """
SELECT deviation_id, title, qe_type, due_date, date_opened, investigator, location, department, product, criticality, module, module_risk_status, open_investigation_status
FROM (
    SELECT DISTINCT ON (f.deviation_id)
        f.deviation_id,
        e.title,
        e.criticality,
        e.module,
        e.module_risk_status,
        e.open_investigation_status,
        ec.qe_type,
        f.due_date,
        f.date_opened,
        di.investigator,
        loc.location,
        dept.department,
        p.name_of_material AS product,
        f.pg_updated_at_timestamp
    FROM fact_qms_event f
    JOIN dim_event e ON e.deviation_id = f.deviation_id
    LEFT JOIN dim_event_classification ec ON ec.event_classification_key = f.event_classification_key
    LEFT JOIN dim_investigator di ON di.investigator_key = f.investigator_key
    LEFT JOIN dim_location loc ON loc.location_key = f.location_key
    LEFT JOIN dim_department dept ON dept.department_key = f.department_key
    LEFT JOIN dim_product p ON p.product_key = f.product_key
    WHERE f.closed_on IS NULL
    -- Some deviation_ids have multiple open fact_qms_event rows (2 confirmed
    -- live, one with 5) — a known, legitimate source-pipeline pattern, not a
    -- bug (see project memory: star_schema). Without deduping here, the same
    -- investigation appeared multiple times in the list with the same id,
    -- breaking React's key-based reconciliation across pagination (rows
    -- appeared "stuck" between pages). DISTINCT ON picks the most recently
    -- updated snapshot per deviation_id as the representative row.
    ORDER BY f.deviation_id, f.pg_updated_at_timestamp DESC NULLS LAST
) dedup
ORDER BY due_date ASC
"""


async def fetch_open_investigations() -> List[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(_OPEN_INVESTIGATIONS_QUERY)


# Cancelled investigations (dim_event.module = 'Cancelled') always have
# closed_on set (202/202 confirmed live) — outside _OPEN_INVESTIGATIONS_QUERY's
# scope entirely. Per the client (2026-07-28), they should still surface in
# the Investigation Details table (always after every genuinely-open
# investigation, ordered by deviation_id) even though they don't count toward
# Total Investigations / stat pills / status cards / chart — those stay
# open-investigations-only. See action_center.py for how the two lists are
# combined.
_CANCELLED_INVESTIGATIONS_QUERY = """
SELECT deviation_id, title, qe_type, due_date, date_opened, investigator, location, department, product, criticality, module, module_risk_status, open_investigation_status
FROM (
    SELECT DISTINCT ON (f.deviation_id)
        f.deviation_id,
        e.title,
        e.criticality,
        e.module,
        e.module_risk_status,
        e.open_investigation_status,
        ec.qe_type,
        f.due_date,
        f.date_opened,
        di.investigator,
        loc.location,
        dept.department,
        p.name_of_material AS product,
        f.pg_updated_at_timestamp
    FROM fact_qms_event f
    JOIN dim_event e ON e.deviation_id = f.deviation_id
    LEFT JOIN dim_event_classification ec ON ec.event_classification_key = f.event_classification_key
    LEFT JOIN dim_investigator di ON di.investigator_key = f.investigator_key
    LEFT JOIN dim_location loc ON loc.location_key = f.location_key
    LEFT JOIN dim_department dept ON dept.department_key = f.department_key
    LEFT JOIN dim_product p ON p.product_key = f.product_key
    WHERE e.module = 'Cancelled'
    ORDER BY f.deviation_id, f.pg_updated_at_timestamp DESC NULLS LAST
) dedup
ORDER BY deviation_id ASC
"""


async def fetch_cancelled_investigations() -> List[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(_CANCELLED_INVESTIGATIONS_QUERY)


async def fetch_module_completion(deviation_ids: List[int]) -> Dict[int, int]:
    """How many of the 4 real generated-content modules exist per deviation_id.

    Degrades to all-zero for a table that doesn't exist yet on the live DB,
    matching generated_content_queries.py's own UndefinedTableError tolerance
    (generated_content.sql is confirmed not yet run there as of 2026-07-24).
    """
    if not deviation_ids:
        return {}

    counts: Dict[int, int] = {d: 0 for d in deviation_ids}
    pool = get_pool()
    async with pool.acquire() as conn:
        for table in _MODULE_COMPLETION_TABLES:
            try:
                rows = await conn.fetch(
                    f"SELECT DISTINCT deviation_id FROM {table} WHERE deviation_id = ANY($1::int[])",
                    deviation_ids,
                )
            except asyncpg.exceptions.UndefinedTableError:
                continue
            for r in rows:
                counts[r["deviation_id"]] += 1
    return counts
