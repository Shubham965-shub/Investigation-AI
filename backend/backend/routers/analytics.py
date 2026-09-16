"""Analytics dashboard endpoint — GET /api/analytics/summary. IQ Score and the CAPA L1-L5
hierarchy are omitted (no backing data exists); the frontend keeps mock data for those."""
from __future__ import annotations

import datetime
import logging
from collections import Counter
from typing import Dict, List, Optional

from fastapi import APIRouter, Query

from backend.db.action_center_queries import QE_TYPE_TO_STAT_LABEL
from backend.db.analytics_queries import fetch_analytics_rows
from backend.schemas.analytics import (
    AnalyticsSummary,
    CapaStatus,
    CategoryCount,
    EventTypeCard,
    FailurePatterns,
    FilterOptions,
    FrequencyRow,
    MonthCount,
    RootCauseStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])

_EVENT_TYPE_ORDER = ["Deviation", "OOS", "OOT", "Market Complaint"]

# Values meaning "explicitly could not be assigned", not "not yet looked at" — excluded from
# the identified/not-identified split and the 6M breakdown below.
_NON_ASSIGNABLE = {"Non Assignable", "Non-Assignable"}

# Approximate mapping of real root_cause_category values onto the Ishikawa/6M scheme; categories
# with no clear fit (including None and _NON_ASSIGNABLE) are left out rather than forced in.
_ROOT_CAUSE_TO_6M: Dict[str, str] = {
    # Man — personnel/human-driven
    "Handling": "Man",
    "Analyst Error": "Man",
    "Analyst": "Man",
    "Personnel": "Man",
    "Man": "Man",
    "Document Handling": "Man",
    # Machine — equipment/instrument/software/systems
    "Instrument": "Machine",
    "Equipment": "Machine",
    "Equipment/Instrument": "Machine",
    "Instrument / Equipment": "Machine",
    "Software": "Machine",
    "Network connectivity": "Machine",
    "Instrument Error": "Machine",
    # Material — raw/input/packing materials
    "Input Material": "Material",
    "Packing Material": "Material",
    "Raw Material": "Material",
    "Material": "Material",
    # Method — process/procedure/SOP/analytical method design
    "Product/Process": "Method",
    "Procedure": "Method",
    "Method": "Method",
    "Analytical Method": "Method",
    "Analytical Method (Spec/STP)": "Method",
    "SOP not followed": "Method",
    "Pack Design": "Method",
    "Protocol/SOP/others": "Method",
    "SOP/WI discribancies": "Method",
    "SOP/WI discrepancies": "Method",
    "Analytical": "Method",
    "Stability Management": "Method",
    "Hold Time Failure": "Method",
    # Measurement — measurement-system-specific
    "Measurement": "Measurement",
    # Mother Nature — environmental
    "Environment": "Mother Nature",
    "Milieu / Environment": "Mother Nature",
}
_6M_ORDER = ["Method", "Material", "Measurement", "Mother Nature", "Man", "Machine"]

_MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Placeholder values meaning "doesn't apply", not a real product/equipment name — left in, they'd
# dominate the frequency charts with a meaningless "N/A" bar.
_NOT_APPLICABLE_VALUES = {"not applicable", "n/a", "na", "none"}


def _is_real_value(value: Optional[str]) -> bool:
    return bool(value) and value.strip().lower() not in _NOT_APPLICABLE_VALUES


def _month_start(d: datetime.date) -> datetime.date:
    return datetime.date(d.year, d.month, 1)


def _shift_month(d: datetime.date, delta: int) -> datetime.date:
    month_index = d.month - 1 + delta
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return datetime.date(year, month, 1)


def _trend_pct(rows: List[Dict], today: datetime.date) -> Optional[float]:
    """% change vs the same elapsed-day window last month (e.g. on the 3rd, Aug 1-3 vs Jul 1-3), not a full-month comparison that would unfairly understate the current month."""
    this_start = _month_start(today)
    last_start = _shift_month(this_start, -1)
    last_end = last_start + (today - this_start)

    this_count = sum(1 for r in rows if r["date_opened"] and this_start <= r["date_opened"] <= today)
    last_count = sum(1 for r in rows if r["date_opened"] and last_start <= r["date_opened"] <= last_end)

    if last_count == 0:
        return None
    return round((this_count - last_count) / last_count * 100, 1)


def _build_event_card(key: str, label: str, rows: List[Dict], trend_rows: List[Dict], today: datetime.date) -> EventTypeCard:
    total = len(rows)
    closed = sum(1 for r in rows if r["open_investigation_status"] == "Closed")
    overdue = sum(1 for r in rows if r["open_investigation_status"] == "Overdue")
    in_progress = total - closed
    return EventTypeCard(
        key=key,
        label=label,
        total=total,
        in_progress=in_progress,
        closed=closed,
        overdue=overdue,
        overdue_pct=round(overdue / total * 100) if total else 0,
        # trend_rows excludes the date-range preset filter, or a "last 30 days"-style preset would
        # exclude last month's data and the trend would always show "no data".
        trend_pct=_trend_pct(trend_rows, today),
    )


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    site: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    equipment: Optional[str] = Query(None),
    start_date_from: Optional[datetime.date] = Query(None, description="Only events opened on/after this date"),
) -> AnalyticsSummary:
    records = await fetch_analytics_rows()
    today = datetime.date.today()
    # pg_updated_at_timestamp is a naive TIMESTAMP; without attaching UTC explicitly, the
    # frontend's IST conversion only works for a viewer whose machine is already set to IST.
    last_updated_at_raw = next((r["pg_updated_at_timestamp"] for r in records if r["pg_updated_at_timestamp"]), None)
    last_updated_at = last_updated_at_raw.replace(tzinfo=datetime.timezone.utc) if last_updated_at_raw else None

    all_rows: List[Dict] = []
    for r in records:
        all_rows.append(
            {
                "deviation_id": r["deviation_id"],
                "date_opened": r["date_opened"].date() if r["date_opened"] else None,
                "capa_record_id": r["capa_record_id"],
                "label": QE_TYPE_TO_STAT_LABEL.get(r["qe_type"], r["qe_type"] or "Unknown"),
                "open_investigation_status": r["open_investigation_status"],
                "root_cause_category": r["root_cause_category"],
                "root_cause_broad_category": r["root_cause_broad_category"],
                "product": r["product"],
                "equipment": r["equipment"],
                "site": r["site"],
                "department": r["department"],
            }
        )

    # Dropdown options reflect the full, unfiltered event population — computed before filtering.
    filter_options = FilterOptions(
        sites=sorted({r["site"] for r in all_rows if r["site"]}),
        departments=sorted({r["department"] for r in all_rows if r["department"]}),
        products=sorted({r["product"] for r in all_rows if _is_real_value(r["product"])}),
        equipment=sorted({r["equipment"] for r in all_rows if _is_real_value(r["equipment"])}),
    )

    categorical_rows = all_rows
    if site:
        categorical_rows = [r for r in categorical_rows if r["site"] == site]
    if department:
        categorical_rows = [r for r in categorical_rows if r["department"] == department]
    if product:
        categorical_rows = [r for r in categorical_rows if r["product"] == product]
    if equipment:
        categorical_rows = [r for r in categorical_rows if r["equipment"] == equipment]

    rows = categorical_rows
    if start_date_from is not None:
        rows = [r for r in rows if r["date_opened"] and r["date_opened"] >= start_date_from]

    # ── Event section ───────────────────────────────────────────────────
    events = [_build_event_card("overall", "Overall Logged", rows, categorical_rows, today)]
    for label in _EVENT_TYPE_ORDER:
        events.append(
            _build_event_card(
                label.lower().replace(" ", "_"),
                label,
                [r for r in rows if r["label"] == label],
                [r for r in categorical_rows if r["label"] == label],
                today,
            )
        )

    # ── Root Cause Status ───────────────────────────────────────────────
    assignable = [r for r in rows if r["root_cause_category"] not in (None, *_NON_ASSIGNABLE)]
    root_cause_status = RootCauseStatus(
        identified=len(assignable),
        not_identified=len(rows) - len(assignable),
        total=len(rows),
    )

    bucket_counts = Counter(
        _ROOT_CAUSE_TO_6M[r["root_cause_category"]]
        for r in rows
        if r["root_cause_category"] in _ROOT_CAUSE_TO_6M
    )
    root_cause_categories = [CategoryCount(label=label, count=bucket_counts.get(label, 0)) for label in _6M_ORDER]

    # ── CAPA Status ─────────────────────────────────────────────────────
    with_capa_rows = [r for r in rows if r["capa_record_id"] is not None]
    without_capa = len(rows) - len(with_capa_rows)

    monthly_trend: List[MonthCount] = []
    for i in range(5, -1, -1):
        bucket_start = _shift_month(_month_start(today), -i)
        bucket_end = _shift_month(bucket_start, 1)
        count = sum(
            1 for r in with_capa_rows
            if r["date_opened"] and bucket_start <= r["date_opened"] < bucket_end
        )
        monthly_trend.append(MonthCount(label=_MONTH_LABELS[bucket_start.month - 1], value=count))

    capa_category_counts = Counter(
        r["root_cause_broad_category"] for r in with_capa_rows if r["root_cause_broad_category"]
    )
    by_root_cause_category = [
        CategoryCount(label=label, count=count)
        for label, count in capa_category_counts.most_common(6)
    ]

    capa = CapaStatus(
        with_capa=len(with_capa_rows),
        without_capa=without_capa,
        total=len(rows),
        monthly_trend=monthly_trend,
        by_root_cause_category=by_root_cause_category,
    )

    # ── Failure Pattern Analysis ────────────────────────────────────────
    product_counts = Counter(r["product"] for r in rows if _is_real_value(r["product"]))
    equipment_counts = Counter(r["equipment"] for r in rows if _is_real_value(r["equipment"]))
    failure_patterns = FailurePatterns(
        products=[FrequencyRow(label=label, value=count) for label, count in product_counts.most_common(8)],
        equipment=[FrequencyRow(label=label, value=count) for label, count in equipment_counts.most_common(8)],
    )

    return AnalyticsSummary(
        events=events,
        root_cause_status=root_cause_status,
        root_cause_categories=root_cause_categories,
        capa=capa,
        failure_patterns=failure_patterns,
        filter_options=filter_options,
        last_updated_at=last_updated_at,
    )