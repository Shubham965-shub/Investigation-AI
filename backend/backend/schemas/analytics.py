"""Response shapes for the Analytics dashboard (GET /api/analytics/summary); only data-groundable sections, see analytics_queries.py for what's excluded."""
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
    # % change in opened count, month-to-date vs same elapsed-day window last month; None if last month had zero comparable events.
    trend_pct: Optional[float] = None


class RootCauseStatus(BaseModel):
    # 2-way split only — no confidence/status column exists to distinguish "confirmed" vs "probable" root cause.
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
    # Substitute for the mock's L1-L5 CAPA hierarchy ranking — capa_effectiveness is 100% NULL, so no such tier exists in the data.
    by_root_cause_category: List[CategoryCount]


class FrequencyRow(BaseModel):
    label: str
    value: int


class FailurePatterns(BaseModel):
    products: List[FrequencyRow]
    equipment: List[FrequencyRow]


class FilterOptions(BaseModel):
    """Distinct values, always from the FULL unfiltered event population so switching one filter never removes other valid options."""

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
    # Same page-level stamp as ActionCenterSummary.last_updated_at, same flat bulk-load caveat.
    last_updated_at: Optional[datetime.datetime] = None