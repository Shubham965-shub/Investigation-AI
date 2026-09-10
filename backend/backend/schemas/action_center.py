"""Response shapes for the Action Center dashboard (GET /api/action-center/summary)."""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class MonthlyBar(BaseModel):
    label: str  # "Mar", "Apr", ... — the 6 most recently COMPLETED calendar months
    count: int


class MonthlyTrend(BaseModel):
    monthly: List[MonthlyBar]
    # Signed % change of the last bar vs. the one before it; None when the
    # prior month's count is 0 (a % change would be undefined/infinite).
    trend_percent: Optional[int] = None


class EventTypeCount(BaseModel):
    label: str
    count: int
    percent: float
    # How many of this event type were CLOSED per month, last 6 complete
    # months, plus the MoM trend — matches the SIT Dashboard Figma mock
    # (node 2255:70409, 2026-09-04, per the user).
    closed_trend: MonthlyTrend


class StatusCard(BaseModel):
    key: str
    label: str
    count: int
    rows: List[List[object]]  # [[bucket_label: str, count: int], ...]


class PendingAction(BaseModel):
    id: str
    title: str
    due_date: Optional[str] = None
    is_overdue: bool
    is_unassigned: bool
    criticality: Optional[str] = None
    action: str
    # Drives the panel's fixed two-row layout: row 1 = top overdue+critical
    # OOS, row 2 = top overdue+critical Deviation (see action_center.py).
    event_type: str


class InvestigationRow(BaseModel):
    id: str
    title: str
    event_type: str
    investigator: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    # CAVEAT (2026-08-03, unresolved) — sourced from fact_qms_event.pg_updated_at_timestamp,
    # confirmed to be a single flat bulk-load stamp (1 distinct value across
    # all 7,246 rows, cancelled included), NOT a real per-investigation
    # update time. See routers/action_center.py for the fuller note and the
    # dim_event.module_start_date/module_end_date candidates being checked
    # with the data engineer as a replacement.
    updated_at: Optional[str] = None
    stage: int
    total_stages: int = 7
    bucket: str  # unassigned | on_track | delay | overdue
    site: Optional[str] = None
    department: Optional[str] = None
    product: Optional[str] = None
    is_cancelled: bool = False
    # fact_qms_event.rci_ids — the full list of RCI record ids ever
    # associated with this deviation (2026-09-03, per the user; a newly
    # found column, not previously used anywhere in this app). Distinct
    # from RciReportRecord's own "RCI Number" (dim_rci.rci_key) elsewhere —
    # this is the QMS-event-level list, not a single report's own id.
    rci_ids: List[str] = Field(default_factory=list)
    # dim_event.escalation_level — real values live as "L1".."L5" or "Not
    # Applicable" (6,627/6,686 rows, since most investigations never escalate).
    escalation_level: Optional[str] = None
    # dim_event.oos_oot_phase — "Phase 1"/"Phase 2" for OOS/OOT events, null
    # otherwise (including for OOS/OOT not yet phased). Drives the Unassigned
    # vs Unassigned – Phase 1 status-card split (see action_center.py).
    oos_oot_phase: Optional[str] = None
    # dim_event.criticality — "Critical"/"Major"/"Minor". Already computed
    # into `enriched`/`cancelled_enriched` for the page's own criticality
    # filter, but wasn't previously surfaced on each row; now used for the
    # investigation table's per-row criticality badge (2026-09-08, per the
    # user).
    criticality: Optional[str] = None


class ChartBar(BaseModel):
    label: str
    on_track: int
    at_risk: int
    delayed: int


class FilterOptions(BaseModel):
    """Distinct real values (from dim_location/dim_department/dim_product/
    dim_investigator, scoped to currently-open investigations) to populate
    the Investigation Details filter dropdowns."""

    sites: List[str]
    departments: List[str]
    products: List[str]
    investigators: List[str]


class ActionCenterSummary(BaseModel):
    total_investigations: int
    event_type_counts: List[EventTypeCount]
    # How many investigations (any type) were OPENED per month, last 6
    # complete months, plus the MoM trend — the "Open Investigations" card's
    # own chart (see EventTypeCount.closed_trend for the per-type version).
    opened_trend: MonthlyTrend
    status_cards: List[StatusCard]
    # Same 4 cards as status_cards, scoped to just that event type — per the
    # user (2026-07-31), clicking a Deviation/OOS/OOT/Market Complaint pill
    # keeps the same card set (not a different drill-down layout) with
    # counts filtered to that type. Keyed by the same labels as
    # event_type_counts (see action_center.py).
    status_cards_by_event_type: Dict[str, List[StatusCard]]
    pending_actions: List[PendingAction]
    chart: List[ChartBar]
    investigations: List[InvestigationRow]
    filter_options: FilterOptions
    # Page-level "last updated" stamp (2026-09-09, per the user) — the raw
    # fact_qms_event.pg_updated_at_timestamp value (a single flat bulk-load
    # stamp shared by every row, see the caveat where investigations are
    # enriched), surfaced verbatim rather than truncated to a date like
    # InvestigationRow.updated_at is. None only if the table itself is
    # completely empty.
    last_updated_at: Optional[datetime.datetime] = None
