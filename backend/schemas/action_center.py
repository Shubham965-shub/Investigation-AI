"""Response shapes for the Action Center dashboard (GET /api/action-center/summary)."""
from __future__ import annotations

from typing import List, Optional

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


class InvestigationRow(BaseModel):
    id: str
    title: str
    event_type: str
    investigator: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
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
    severity_cards: List[StatusCard]
    pending_actions: List[PendingAction]
    chart: List[ChartBar]
    investigations: List[InvestigationRow]
    filter_options: FilterOptions
