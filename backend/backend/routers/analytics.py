"""Analytics dashboard endpoint — GET /api/analytics/summary.

Scope (2026-08-03, per the user): only sections that map cleanly onto real
star-schema columns are computed here — Event, CAPA presence, Root Cause
presence, and Failure Pattern frequency. Investigation Quality (IQ Score) and
the CAPA L1-L5 hierarchy ranking have no backing data anywhere (verified
against the live DB) and are intentionally left out of this response — the
frontend keeps its mock data for those two sections until a real formula/
mapping is defined.
"""
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

# root_cause_category free-text values that mean "explicitly could not be
# assigned" rather than "not yet looked at" — excluded from both the
# identified/not-identified split and the 6M breakdown below. Distinct
# values verified against the live DB (2026-08-03).
_NON_ASSIGNABLE = {"Non Assignable", "Non-Assignable"}

# Best-effort mapping of real root_cause_category values (verified against
# the live DB, 39 distinct values total) onto the Figma mock's Ishikawa/6M
# scheme (Man/Machine/Material/Method/Measurement/Mother Nature) — per the
# user, keep the 6M labels rather than relabel the chart to real category
# names. This is necessarily approximate: the real taxonomy doesn't actually
# follow a 6M structure. Only categories with a clear conceptual fit are
# mapped; anything else (including None and _NON_ASSIGNABLE) is left out of
# the chart entirely rather than forced into a bucket.
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

# dim_product.name_of_material/dim_equipment.instrument_equipment placeholder
# values meaning "doesn't apply to this event" rather than a real product/
# equipment name — verified as the single largest value for both columns on
# the live DB (853/6,686 products, 2,256/6,686 equipment). Left in, they'd
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
    """% change in newly-opened count, current month-to-date vs the same
    elapsed-day window last month — e.g. on the 3rd, compares Aug 1-3
    against Jul 1-3, not the (still-incomplete) full current month against
    a full prior month, which would understate the current month unfairly."""
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
        # Trend is always a fixed month-over-month comparison — computed
        # from trend_rows (site/dept/product/equipment filters applied, but
        # NOT the date-range preset), since applying a "last 30 days"-style
        # preset to the same rows used for the comparison would exclude last
        # month's data entirely and make the trend always show "no data".
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

    # Dropdown options always reflect the full, unfiltered event population
    # (see FilterOptions' docstring) — computed before any filter below is
    # applied to `rows`. "Not Applicable"-style placeholders are excluded
    # here too, same reasoning as the Failure Pattern frequency counts.
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
    )