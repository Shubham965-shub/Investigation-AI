"""Queries backing the Action Center dashboard.

Scoped to OPEN investigations only (closed_on IS NULL — the authoritative
close date; date_closed is a separate field that can be set on rows still
genuinely open, so it must not be used for this filter).

- Progress chart: bucketed by dim_event.module, excluding module='Cancelled';
  on_track/at_risk/delayed stacking comes from dim_event.module_risk_status.
- Status cards: bucketed from dim_event.open_investigation_status directly.
- Per-row stage (X/6 steps): module_stage.stage_for(dim_event.module) —
  fetch_module_completion() below is no longer called, kept in case it's
  needed again.
- Pending actions: unassigned/overdue cases, described by the next module
  label after the investigation's current stage.
"""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

import asyncpg

from backend.clients.db_client import get_pool

# Order matches the first 4 entries of module_stage.MODULE_LABELS. Task
# Critique/RCI Report have no backing tables yet and are excluded.
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

# Open investigations opened before this date are excluded from Action
# Center entirely (table, stats, chart). Scoped to _OPEN_INVESTIGATIONS_QUERY
# only; the cancelled-investigations query is untouched.
OPEN_INVESTIGATIONS_SINCE = datetime.date(2026, 1, 1)

_OPEN_INVESTIGATIONS_QUERY = """
WITH investigator_by_rci AS (
    -- Each fact_qms_event row for a deviation_id can have its own distinct
    -- rci_key/investigator (e.g. one deviation split across two RCI ids,
    -- each with a different investigator) — mapped here so each frontend
    -- row (exploded per rci_id) shows its own investigator, not whichever
    -- single one the dedup below happened to keep.
    SELECT
        f.deviation_id,
        jsonb_object_agg(f.rci_key::text, di.investigator) FILTER (WHERE f.rci_key IS NOT NULL) AS investigator_by_rci
    FROM fact_qms_event f
    LEFT JOIN dim_investigator di ON di.investigator_key = f.investigator_key
    GROUP BY f.deviation_id
)
SELECT dedup.deviation_id, title, qe_type, due_date, due_date_display, extended_due_date, date_opened, investigator, location, department, product, criticality, event_classification, oos_oot_phase, escalation_level, module, module_risk_status, open_investigation_status, pg_updated_at_timestamp, rci_ids, investigator_by_rci
FROM (
    SELECT DISTINCT ON (f.deviation_id)
        f.deviation_id,
        e.title,
        e.criticality,
        e.event_classification,
        e.oos_oot_phase,
        e.escalation_level,
        e.module,
        e.module_risk_status,
        e.open_investigation_status,
        ec.qe_type,
        f.due_date,
        f.due_date_display,
        f.extended_due_date,
        f.date_opened,
        di.investigator,
        loc.location,
        dept.department,
        p.name_of_material AS product,
        f.pg_updated_at_timestamp,
        f.rci_ids
    FROM fact_qms_event f
    JOIN dim_event e ON e.deviation_id = f.deviation_id
    LEFT JOIN dim_event_classification ec ON ec.event_classification_key = f.event_classification_key
    LEFT JOIN dim_investigator di ON di.investigator_key = f.investigator_key
    LEFT JOIN dim_location loc ON loc.location_key = f.location_key
    LEFT JOIN dim_department dept ON dept.department_key = f.department_key
    LEFT JOIN dim_product p ON p.product_key = f.product_key
    WHERE f.closed_on IS NULL
    AND f.date_opened >= $1
    -- Some deviation_ids have multiple open fact_qms_event rows (legitimate
    -- source-pipeline pattern, not a bug) — dedup here so the same
    -- investigation doesn't appear twice with the same id and break React's
    -- key-based pagination. Ordered by rci_key (not pg_updated_at_timestamp,
    -- which is a flat bulk-load stamp identical on every row and so not a
    -- real tiebreaker) for a deterministic pick; investigator itself comes
    -- from investigator_by_rci above regardless of which row wins here.
    ORDER BY f.deviation_id, f.rci_key DESC NULLS LAST, f.composite_primary_key
) dedup
LEFT JOIN investigator_by_rci ir ON ir.deviation_id = dedup.deviation_id
ORDER BY due_date ASC
"""


async def fetch_open_investigations() -> List[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(_OPEN_INVESTIGATIONS_QUERY, OPEN_INVESTIGATIONS_SINCE)


# Cancelled investigations (module='Cancelled') always have closed_on set,
# outside _OPEN_INVESTIGATIONS_QUERY's scope — still shown in the
# Investigation Details table (after every open investigation) but excluded
# from stats/chart. See action_center.py for how the two lists combine.
_CANCELLED_INVESTIGATIONS_QUERY = """
WITH investigator_by_rci AS (
    -- Same per-rci_key investigator map as _OPEN_INVESTIGATIONS_QUERY's CTE.
    SELECT
        f.deviation_id,
        jsonb_object_agg(f.rci_key::text, di.investigator) FILTER (WHERE f.rci_key IS NOT NULL) AS investigator_by_rci
    FROM fact_qms_event f
    LEFT JOIN dim_investigator di ON di.investigator_key = f.investigator_key
    GROUP BY f.deviation_id
)
SELECT dedup.deviation_id, title, qe_type, due_date, due_date_display, extended_due_date, date_opened, investigator, location, department, product, criticality, event_classification, oos_oot_phase, escalation_level, module, module_risk_status, open_investigation_status, pg_updated_at_timestamp, rci_ids, investigator_by_rci
FROM (
    SELECT DISTINCT ON (f.deviation_id)
        f.deviation_id,
        e.title,
        e.criticality,
        e.event_classification,
        e.oos_oot_phase,
        e.escalation_level,
        e.module,
        e.module_risk_status,
        e.open_investigation_status,
        ec.qe_type,
        f.due_date,
        f.due_date_display,
        f.extended_due_date,
        f.date_opened,
        di.investigator,
        loc.location,
        dept.department,
        p.name_of_material AS product,
        f.pg_updated_at_timestamp,
        f.rci_ids
    FROM fact_qms_event f
    JOIN dim_event e ON e.deviation_id = f.deviation_id
    LEFT JOIN dim_event_classification ec ON ec.event_classification_key = f.event_classification_key
    LEFT JOIN dim_investigator di ON di.investigator_key = f.investigator_key
    LEFT JOIN dim_location loc ON loc.location_key = f.location_key
    LEFT JOIN dim_department dept ON dept.department_key = f.department_key
    LEFT JOIN dim_product p ON p.product_key = f.product_key
    WHERE e.module = 'Cancelled'
    -- Same pg_updated_at_timestamp tiebreaker fix as _OPEN_INVESTIGATIONS_QUERY.
    ORDER BY f.deviation_id, f.rci_key DESC NULLS LAST, f.composite_primary_key
) dedup
LEFT JOIN investigator_by_rci ir ON ir.deviation_id = dedup.deviation_id
ORDER BY deviation_id ASC
"""


async def fetch_cancelled_investigations() -> List[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(_CANCELLED_INVESTIGATIONS_QUERY)


# Full static department list from dim_department, not just departments with
# an open investigation today (only 9 of 22 do) — unlike sites/products/
# investigators, which stay dynamic to what's actually present.
async def fetch_all_departments() -> List[str]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT department FROM dim_department WHERE department IS NOT NULL ORDER BY department")
        return [r["department"] for r in rows]


# Backs the KPI cards' monthly bar chart + MoM trend — unlike
# _OPEN_INVESTIGATIONS_QUERY, covers the full event population (cancelled
# excluded), pulled as one flat row set and bucketed by month in Python.
# Matches on EITHER date_opened or closed_on since the same row feeds both
# the "opened per month" and "closed per month" charts.
_MONTHLY_TREND_ROWS_QUERY = """
SELECT deviation_id, qe_type, date_opened, closed_on
FROM (
    SELECT DISTINCT ON (f.deviation_id)
        f.deviation_id,
        ec.qe_type,
        f.date_opened,
        f.closed_on,
        e.module,
        di.investigator,
        f.pg_updated_at_timestamp
    FROM fact_qms_event f
    JOIN dim_event e ON e.deviation_id = f.deviation_id
    LEFT JOIN dim_event_classification ec ON ec.event_classification_key = f.event_classification_key
    LEFT JOIN dim_investigator di ON di.investigator_key = f.investigator_key
    WHERE f.date_opened >= $1 OR f.closed_on >= $1
    ORDER BY f.deviation_id, f.pg_updated_at_timestamp DESC NULLS LAST
) dedup
WHERE module IS DISTINCT FROM 'Cancelled'
  AND ($2::text IS NULL OR lower(trim(investigator)) = lower(trim($2)))
"""


async def fetch_monthly_trend_rows(since: datetime.date, investigator: Optional[str] = None) -> List[asyncpg.Record]:
    """investigator optionally scopes the KPI charts to one investigator
    (Investigator role) — applied independently since this is a separate
    query from _OPEN_INVESTIGATIONS_QUERY."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(_MONTHLY_TREND_ROWS_QUERY, since, investigator)


async def fetch_module_completion(deviation_ids: List[int]) -> Dict[int, int]:
    """How many of the 4 real generated-content modules exist per deviation_id
    (degrades to all-zero if the backing table doesn't exist yet)."""
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
