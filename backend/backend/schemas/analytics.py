"""Response shapes for the Analytics dashboard (GET /api/analytics/summary).

Only the data-groundable sections (Event, CAPA presence, Root Cause presence,
Failure Pattern frequency) are covered — see analytics_queries.py's module
docstring for what's deliberately NOT here (IQ Score, CAPA hierarchy ranking).
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from pydantic import BaseModel


class EventTypeCard(BaseModel):
    key: str
    label: str
    total: int
    in_progress: int
    closed: int
    overdue: int
    overdue_pct: int
    # % change in newly-opened count, current month-to-date vs the same
    # elapsed-day window last month (see routers/analytics.py). None when
    # last month has zero comparable events (undefined % change).
    trend_pct: Optional[float] = None


class RootCauseStatus(BaseModel):
    # 2-way split only — real data has no signal distinguishing "confirmed"
    # from "probable" root cause (no confidence/status column anywhere on
    # dim_event or dim_rci), so the mock's 3-tier Identified/Probable/None
    # split is deliberately not reproduced. See routers/analytics.py.
    identified: int
    not_identified: int
    total: int


class CategoryCount(BaseModel):
    label: str
    count: int


class MonthCount(BaseModel):
    label: str
    value: int


class CapaStatus(BaseModel):
    with_capa: int
    without_capa: int
    total: int
    monthly_trend: List[MonthCount]
    # Replaces the mock's L1-L5 hierarchy ranking (Error Proofing / Error
    # Prevention / ...) — no such tier exists anywhere in the star schema
    # (capa_effectiveness is 100% NULL, confirmed against the live DB). This
    # is a real, groundable substitute: which root-cause categories the
    # CAPA'd events actually fall under.
    by_root_cause_category: List[CategoryCount]


class FrequencyRow(BaseModel):
    label: str
    value: int


class FailurePatterns(BaseModel):
    products: List[FrequencyRow]
    equipment: List[FrequencyRow]


class FilterOptions(BaseModel):
    """Distinct real values (from dim_location/dim_department/dim_product/
    dim_equipment) — always computed from the FULL, unfiltered event
    population, not narrowed by whichever filters are currently applied, so
    switching any one filter never removes other still-valid options."""

    sites: List[str]
    departments: List[str]
    products: List[str]
    equipment: List[str]


class AnalyticsSummary(BaseModel):
    events: List[EventTypeCard]
    root_cause_status: RootCauseStatus
    root_cause_categories: List[CategoryCount]
    capa: CapaStatus
    failure_patterns: FailurePatterns
    filter_options: FilterOptions
    # Same page-level "last updated" stamp as ActionCenterSummary's own field
    # (2026-09-09, per the user) — see that field's docstring for the
    # single-flat-bulk-load-stamp caveat this is built on.
    last_updated_at: Optional[datetime.datetime] = None