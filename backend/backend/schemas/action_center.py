"""Response shapes for the Action Center dashboard (GET /api/action-center/summary)."""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel


class EventTypeCount(BaseModel):
    label: str
    count: int
    percent: int


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
