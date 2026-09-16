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
    # % change vs prior month; None if prior month count is 0 (undefined).
    trend_percent: Optional[int] = None


class EventTypeCount(BaseModel):
    label: str
    count: int
    percent: float
    # Closed count per month, last 6 complete months, plus MoM trend.
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
    # Drives the panel's fixed two-row layout: row 1 = OOS, row 2 = Deviation.
    event_type: str


class InvestigationRow(BaseModel):
    id: str
    title: str
    event_type: str
    investigator: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    # pg_updated_at_timestamp is a flat bulk-load stamp, same value on every row — NOT a real per-investigation "last updated" time.
    updated_at: Optional[str] = None
    stage: int
    total_stages: int = 7
    bucket: str  # unassigned | on_track | delay | overdue
    site: Optional[str] = None
    department: Optional[str] = None
    product: Optional[str] = None
    is_cancelled: bool = False
    # fact_qms_event.rci_ids — all RCI record ids ever tied to this deviation; distinct from dim_rci.rci_key elsewhere.
    rci_ids: List[str] = Field(default_factory=list)
    # dim_event.escalation_level — "L1".."L5" or "Not Applicable" (most investigations never escalate).
    escalation_level: Optional[str] = None
    # dim_event.oos_oot_phase — "Phase 1"/"Phase 2" for OOS/OOT, else null. Drives the Unassigned vs Unassigned-Phase 1 split.
    oos_oot_phase: Optional[str] = None
    # dim_event.criticality — binary, always exactly "Critical"/"Non-Critical" (not a Major/Minor tier; that's event_classification below).
    criticality: Optional[str] = None
    # dim_event.event_classification — separate from criticality above: "Critical"/"Major"/"Minor", or None (OOS/OOT, unclassified, or N/A Complaint).
    event_classification: Optional[str] = None
    # SIT Dashboard's per-row free-text remark, keyed by rci_id ("" if none). Only populated for SIT-role callers, {} otherwise.
    remarks: Dict[str, str] = Field(default_factory=dict)
    # Per-rci_id investigator — a deviation's RCIs can have different investigators, unlike the single `investigator` field above.
    investigator_by_rci: Dict[str, Optional[str]] = Field(default_factory=dict)


class RemarkUpdateRequest(BaseModel):
    # "" means this row has no RCI ID — see InvestigationRow.remarks above.
    rci_id: str = ""
    remark: str


class ChartBar(BaseModel):
    label: str
    on_track: int
    at_risk: int
    delayed: int


class FilterOptions(BaseModel):
    """Distinct values for the Investigation Details filter dropdowns, scoped to currently-open investigations."""

    sites: List[str]
    departments: List[str]
    products: List[str]
    investigators: List[str]


class ActionCenterSummary(BaseModel):
    total_investigations: int
    event_type_counts: List[EventTypeCount]
    # Opened count per month, last 6 complete months, plus MoM trend — feeds the "Open Investigations" card.
    opened_trend: MonthlyTrend
    status_cards: List[StatusCard]
    # Same 4 cards as status_cards, filtered per event type; keyed by the same labels as event_type_counts.
    status_cards_by_event_type: Dict[str, List[StatusCard]]
    pending_actions: List[PendingAction]
    chart: List[ChartBar]
    investigations: List[InvestigationRow]
    filter_options: FilterOptions
    # Page-level stamp — raw pg_updated_at_timestamp (same flat bulk-load caveat as InvestigationRow.updated_at), unlike that field not truncated to a date.
    last_updated_at: Optional[datetime.datetime] = None
