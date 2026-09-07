from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from backend.db.action_center_queries import (
    QE_TYPE_TO_STAT_LABEL,
    fetch_cancelled_investigations,
    fetch_monthly_trend_rows,
    fetch_open_investigations,
)
from backend.db.module_stage import MODULE_LABELS, next_module_label, stage_for
from backend.schemas.action_center import (
    ActionCenterSummary,
    ChartBar,
    EventTypeCount,
    FilterOptions,
    InvestigationRow,
    MonthlyBar,
    MonthlyTrend,
    PendingAction,
    StatusCard,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/action-center", tags=["Action Center"])

_PENDING_ACTIONS_PER_ROW = 3

_EVENT_TYPE_ORDER = ["Deviation", "OOS", "OOT", "Market Complaint"]

# KPI card monthly bar chart + MoM trend (SIT Dashboard Figma, 2026-09-04,
# per the user) — the 6 most recently COMPLETED calendar months, excluding
# the current in-progress one, matching the Figma mock's own Mar-Aug window.
_TREND_MONTHS = 6


def _month_starts(n: int, today: datetime.date) -> List[datetime.date]:
    """n calendar month-start dates, oldest first, ending with the most
    recently completed month (e.g. run on 2026-09-04 with n=6 gives
    Mar-Aug 2026, never a partial September)."""
    months = []
    cursor = today.replace(day=1)
    for _ in range(n):
        cursor = (cursor - datetime.timedelta(days=1)).replace(day=1)
        months.append(cursor)
    return list(reversed(months))


def _bucket_monthly(rows: List[Dict[str, Any]], date_key: str, months: List[datetime.date]) -> List[MonthlyBar]:
    counts = {m: 0 for m in months}
    for row in rows:
        d = row.get(date_key)
        if d is None:
            continue
        # fact_qms_event.date_opened/closed_on are TIMESTAMPs (datetime, with
        # a time-of-day component), not plain dates — .date() first, or
        # .replace(day=1) below would produce a datetime that never equals
        # (or hashes equal to) the plain `date` keys in `counts`, silently
        # zeroing every bucket (confirmed live, 2026-09-04).
        if isinstance(d, datetime.datetime):
            d = d.date()
        month_start = d.replace(day=1)
        if month_start in counts:
            counts[month_start] += 1
    return [MonthlyBar(label=m.strftime("%b"), count=counts[m]) for m in months]


def _trend_percent(monthly: List[MonthlyBar]) -> Optional[int]:
    if len(monthly) < 2 or monthly[-2].count == 0:
        return None
    return round((monthly[-1].count - monthly[-2].count) / monthly[-2].count * 100)

# Sentinel the Investigator filter uses to mean "no investigator assigned" —
# per the user (2026-07-31). Sent/received as a plain investigator= query
# value, same as a real name, just matched against a null/blank investigator
# instead of an equality check. Unlikely enough to collide with a real name
# that no extra guarding is needed.
_UNASSIGNED_INVESTIGATOR_FILTER = "__unassigned__"

# Chart-only grouping (per the user, 2026-07-31): Problem Statement, Evidence
# Collection and Interview Questionnaire — the first 3 of MODULE_LABELS —
# are merged into a single bar, labelled with all 3 names stacked one below
# the other (see StatusChart.tsx's "\n"-split rendering). MODULE_LABELS
# itself is untouched — it still drives stage_for()/next_module_label() and
# the Investigation Details "X/6 steps" progress fraction, which must keep
# counting all 6 real modules individually.
_CHART_MERGED_GROUP = ["Problem Statement", "Evidence Collection", "Interview Questionnaire"]
_CHART_MERGED_LABEL = "\n".join(_CHART_MERGED_GROUP)

# dim_event.module (Trackwise's own current-stage field, renamed from
# `status` on 2026-07-27 — see project memory: star_schema) mapped to the
# chart's module labels, per the backend engineer (2026-07-28): the chart is
# meant to show open investigations segmented by their real current module.
# Matched case/whitespace-insensitively (see the .strip().lower() call below)
# since dim_event.module's real text already drifted once mid-project without
# a corresponding etl_table_metadata timestamp change — both the original
# verbose lowercase values (2026-07-24/27) and the shorter Title Case values
# (2026-07-28: "RCI Report", "RCI Plan", "RC & CAPA Critique") are kept here
# for resilience against a future revert. "problem statement"/"evidence
# collection" haven't been observed in live data under either spelling yet —
# confirm the exact text with the engineer once real rows reach those stages.
# "root cause and capa critique"/"RC & CAPA Critique" -> "Task Critique"
# confirmed by the engineer (2026-07-28) as a graph-only clumping — it's
# actually a separate module in its own right, just grouped into the Task
# Critique bar for this chart specifically; don't treat the two as the same
# module anywhere else.
_MODULE_TEXT_TO_LABEL: Dict[str, str] = {
    "problem statement": "Problem Statement",
    "evidence collection": "Evidence Collection",
    "interview questionnaire": "Interview Questionnaire",
    "rci plan": "RCI Plan Creation",
    "root cause and capa critique": "Task Critique",
    "rc & capa critique": "Task Critique",
    "rci report generation": "RCI Report",
    "rci report": "RCI Report",
}

# Not a real module stage — cancelled investigations are excluded from the
# progress chart entirely and shown as a "Cancelled" pill instead of a
# progress bar in the investigations table (backend engineer, 2026-07-28).
_CANCELLED_MODULE_VALUE = "Cancelled"

# dim_event.module_risk_status -> which of the chart's 3 stacked series a row
# counts toward. "Unknown" has no series to fall into today; it has only ever
# been observed alongside module=None, which is already excluded from the
# chart (no label to bucket into), so it never actually needs a bucket.
_MODULE_RISK_TO_KEY: Dict[str, str] = {
    "Closed": "on_track",
    "At Risk": "at_risk",
    "Delayed": "delayed",
}

# dim_event.open_investigation_status -> the dashboard's internal bucket key.
# Replaces the day-threshold heuristic previously used as a placeholder here
# (see project memory: star_schema) — per the backend engineer (2026-07-28),
# the 4-card/6-card status views should read this column directly.
_OPEN_STATUS_TO_BUCKET: Dict[str, str] = {
    "Unassigned": "unassigned",
    "On Track": "on_track",
    "At Risk": "delay",
    "Overdue": "overdue",
}


def _fmt_date(d: Optional[datetime.date]) -> Optional[str]:
    return d.strftime("%d %b %Y") if d else None


def _bucket_for(open_investigation_status: Optional[str]) -> str:
    return _OPEN_STATUS_TO_BUCKET.get(open_investigation_status, "unassigned")


@router.get("/summary", response_model=ActionCenterSummary)
async def get_action_center_summary(
    site: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    product: Optional[str] = Query(None),
    investigator: Optional[str] = Query(None),
    start_date_from: Optional[datetime.date] = Query(None, description="Only investigations opened on/after this date"),
    start_date_to: Optional[datetime.date] = Query(None, description="Only investigations opened on/before this date"),
    criticality: Optional[str] = Query(
        None,
        description="'critical' or 'non_critical' (2026-08-14, per the user) — applies page-wide (stat "
        "cards/chart/pending actions/investigations table alike), same as site/department/product/"
        "investigator/date, unlike the table-only `status` filter above. 'non_critical' matches anything "
        "not exactly dim_event.criticality = 'Critical' (including NULL), mirroring the existing "
        "criticality != 'Critical' check already used for the status cards/pending actions below.",
    ),
    oos_oot_phase: Optional[str] = Query(
        None,
        description="'phase1' or 'phase2' (2026-08-25, per the user) — the OOS/OOT-only equivalent of "
        "`criticality`'s Major/Minor tiers, replacing them for those two event types specifically. "
        "Applies page-wide, same places `criticality` does, matching against "
        "dim_event.oos_oot_phase = 'Phase 1' / 'Phase 2'.",
    ),
    status: Optional[str] = Query(
        None,
        description="'open' (default, omitted, or any other value) or 'cancelled' — which set the "
        "investigations list itself contains (2026-08-13, per the user: cancelled investigations "
        "should no longer appear in the normal/default view at all, only behind an explicit toggle). "
        "Stat cards/chart/pending actions are unaffected either way — they've always been open-only.",
    ),
) -> ActionCenterSummary:
    rows = await fetch_open_investigations()
    cancelled_rows = await fetch_cancelled_investigations()
    today = datetime.date.today()

    enriched: List[Dict[str, Any]] = []
    for r in rows:
        due_date = r["due_date"].date() if r["due_date"] else None
        date_opened = r["date_opened"].date() if r["date_opened"] else None
        # CAVEAT (2026-08-03, unresolved): pg_updated_at_timestamp is a single
        # flat bulk-load stamp — every row in fact_qms_event (7,246/7,246,
        # including cancelled/closed ones) shares the exact same value, so
        # this is NOT a genuine per-investigation "last updated" signal, just
        # whenever this table was last reloaded. dim_event.module_start_date/
        # module_end_date have real per-row variation and look like better
        # candidates, but their exact semantics need confirming with the data
        # engineer before switching — don't trust this field's UI meaning
        # until that's resolved.
        updated_at = r["pg_updated_at_timestamp"].date() if r["pg_updated_at_timestamp"] else None
        days_until_due = (due_date - today).days if due_date else None
        days_since_opened = (today - date_opened).days if date_opened else 0
        # Table progress bar is driven by Trackwise's own module/state (via
        # module_stage.stage_for — the same "state change detection" mapping
        # the 4 individual module pages already use), NOT the generated-
        # content-table completion count. Per the user (2026-07-28):
        # dim_event.module + _MODULE_TEXT_TO_LABEL below is for the progress
        # chart's bucketing/stacking only — this is "the other one" for the
        # table's per-row progress bar specifically.
        stage = stage_for(r["module"])
        enriched.append(
            {
                "id": str(r["deviation_id"]),
                "title": r["title"] or "Untitled Investigation",
                "qe_type": r["qe_type"],
                "investigator": r["investigator"],
                "site": r["location"],
                "department": r["department"],
                "product": r["product"],
                "criticality": r["criticality"],
                "oos_oot_phase": r["oos_oot_phase"],
                "escalation_level": r["escalation_level"],
                "due_date": due_date,
                "date_opened": date_opened,
                "updated_at": updated_at,
                "days_until_due": days_until_due,
                "days_since_opened": days_since_opened,
                "stage": stage,
                "bucket": _bucket_for(r["open_investigation_status"]),
                "module": r["module"],
                "module_risk_status": r["module_risk_status"],
                "is_cancelled": r["module"] == _CANCELLED_MODULE_VALUE,
                "rci_ids": list(r["rci_ids"]) if r["rci_ids"] else [],
            }
        )

    # Cancelled investigations (dim_event.module = 'Cancelled') — per the
    # client (2026-07-28): shown in the Investigation Details table, always
    # after every genuinely-open investigation, ordered by deviation_id
    # among themselves. Deliberately kept out of `enriched` — they must NOT
    # affect Total Investigations, the event-type stat pills, status/severity
    # cards, or the progress chart (client-confirmed scope: table only).
    cancelled_enriched: List[Dict[str, Any]] = []
    for r in cancelled_rows:
        due_date = r["due_date"].date() if r["due_date"] else None
        date_opened = r["date_opened"].date() if r["date_opened"] else None
        updated_at = r["pg_updated_at_timestamp"].date() if r["pg_updated_at_timestamp"] else None  # see caveat above
        cancelled_enriched.append(
            {
                "deviation_id": r["deviation_id"],
                "id": str(r["deviation_id"]),
                "title": r["title"] or "Untitled Investigation",
                "qe_type": r["qe_type"],
                "investigator": r["investigator"],
                "site": r["location"],
                "department": r["department"],
                "product": r["product"],
                "criticality": r["criticality"],
                "oos_oot_phase": r["oos_oot_phase"],
                "escalation_level": r["escalation_level"],
                "due_date": due_date,
                "date_opened": date_opened,
                "updated_at": updated_at,
                "bucket": _bucket_for(r["open_investigation_status"]),
                "rci_ids": list(r["rci_ids"]) if r["rci_ids"] else [],
            }
        )

    # Order by start date (date_opened), newest first — not the raw query's
    # due_date order. Without this, switching between overlapping filters
    # (e.g. "last week" vs "last month") reshuffled rows unpredictably since
    # nothing was ever actually sorted by start date. Rows with no
    # date_opened always sort to the end.
    with_date = [i for i in enriched if i["date_opened"] is not None]
    without_date = [i for i in enriched if i["date_opened"] is None]
    with_date.sort(key=lambda i: i["date_opened"], reverse=True)
    enriched = with_date + without_date

    # Site/department/product filter dropdowns always reflect the full
    # open-investigation set — not narrowed by whichever filter is currently
    # selected, so users can always switch to any other real value.
    #
    # The investigator dropdown is the exception (per the user, 2026-07-28):
    # it's scoped to whichever investigators actually appear in the table
    # under the OTHER active filters (site/department/product/date), so it
    # only ever lists investigators genuinely present in what's currently
    # shown — computed here, before the investigator filter itself narrows
    # `enriched` further below (an investigator filter narrowing its own
    # dropdown to just the one selected value would be circular/useless).
    scoped_for_investigator_options = enriched
    if site:
        scoped_for_investigator_options = [i for i in scoped_for_investigator_options if i["site"] == site]
    if department:
        scoped_for_investigator_options = [i for i in scoped_for_investigator_options if i["department"] == department]
    if product:
        scoped_for_investigator_options = [i for i in scoped_for_investigator_options if i["product"] == product]
    if criticality == "critical":
        scoped_for_investigator_options = [i for i in scoped_for_investigator_options if i["criticality"] == "Critical"]
    elif criticality == "non_critical":
        scoped_for_investigator_options = [i for i in scoped_for_investigator_options if i["criticality"] != "Critical"]
    if oos_oot_phase == "phase1":
        scoped_for_investigator_options = [i for i in scoped_for_investigator_options if i["oos_oot_phase"] == "Phase 1"]
    elif oos_oot_phase == "phase2":
        scoped_for_investigator_options = [i for i in scoped_for_investigator_options if i["oos_oot_phase"] == "Phase 2"]
    if start_date_from is not None:
        scoped_for_investigator_options = [
            i for i in scoped_for_investigator_options if i["date_opened"] and i["date_opened"] >= start_date_from
        ]
    if start_date_to is not None:
        scoped_for_investigator_options = [
            i for i in scoped_for_investigator_options if i["date_opened"] and i["date_opened"] <= start_date_to
        ]

    investigator_options = sorted({i["investigator"] for i in scoped_for_investigator_options if i["investigator"]})
    # "Unassigned" only appears when at least one investigation in the
    # current (site/department/product/date-scoped) view actually has no
    # investigator — same "only list what's genuinely present" rule the
    # real names already follow (see comment above).
    if any(not i["investigator"] for i in scoped_for_investigator_options):
        investigator_options = [_UNASSIGNED_INVESTIGATOR_FILTER] + investigator_options

    filter_options = FilterOptions(
        sites=sorted({i["site"] for i in enriched if i["site"]}),
        departments=sorted({i["department"] for i in enriched if i["department"]}),
        products=sorted({i["product"] for i in enriched if i["product"]}),
        investigators=investigator_options,
    )

    if site:
        enriched = [i for i in enriched if i["site"] == site]
    if department:
        enriched = [i for i in enriched if i["department"] == department]
    if product:
        enriched = [i for i in enriched if i["product"] == product]
    if investigator:
        if investigator == _UNASSIGNED_INVESTIGATOR_FILTER:
            enriched = [i for i in enriched if not i["investigator"]]
        else:
            enriched = [i for i in enriched if i["investigator"] == investigator]
    if criticality == "critical":
        enriched = [i for i in enriched if i["criticality"] == "Critical"]
    elif criticality == "non_critical":
        enriched = [i for i in enriched if i["criticality"] != "Critical"]
    if oos_oot_phase == "phase1":
        enriched = [i for i in enriched if i["oos_oot_phase"] == "Phase 1"]
    elif oos_oot_phase == "phase2":
        enriched = [i for i in enriched if i["oos_oot_phase"] == "Phase 2"]
    if start_date_from is not None:
        enriched = [i for i in enriched if i["date_opened"] and i["date_opened"] >= start_date_from]
    if start_date_to is not None:
        enriched = [i for i in enriched if i["date_opened"] and i["date_opened"] <= start_date_to]

    # Same filters, applied to cancelled investigations too, then ordered by
    # deviation_id — this is the list that gets appended after `enriched`
    # further down, always landing on the last page(s).
    if site:
        cancelled_enriched = [i for i in cancelled_enriched if i["site"] == site]
    if department:
        cancelled_enriched = [i for i in cancelled_enriched if i["department"] == department]
    if product:
        cancelled_enriched = [i for i in cancelled_enriched if i["product"] == product]
    if investigator:
        if investigator == _UNASSIGNED_INVESTIGATOR_FILTER:
            cancelled_enriched = [i for i in cancelled_enriched if not i["investigator"]]
        else:
            cancelled_enriched = [i for i in cancelled_enriched if i["investigator"] == investigator]
    if criticality == "critical":
        cancelled_enriched = [i for i in cancelled_enriched if i["criticality"] == "Critical"]
    elif criticality == "non_critical":
        cancelled_enriched = [i for i in cancelled_enriched if i["criticality"] != "Critical"]
    if oos_oot_phase == "phase1":
        cancelled_enriched = [i for i in cancelled_enriched if i["oos_oot_phase"] == "Phase 1"]
    elif oos_oot_phase == "phase2":
        cancelled_enriched = [i for i in cancelled_enriched if i["oos_oot_phase"] == "Phase 2"]
    if start_date_from is not None:
        cancelled_enriched = [i for i in cancelled_enriched if i["date_opened"] and i["date_opened"] >= start_date_from]
    if start_date_to is not None:
        cancelled_enriched = [i for i in cancelled_enriched if i["date_opened"] and i["date_opened"] <= start_date_to]
    cancelled_enriched.sort(key=lambda i: i["deviation_id"])

    total = len(enriched)

    # ── Event type breakdown ──────────────────────────────────────────
    # Fixed display order (Deviation, OOS, OOT, Market Complaint) matches
    # Figma exactly — not sorted by count, which would reshuffle the pills
    # as the data changes. All 4 always show, even at count 0 (2026-08-21,
    # per the user) — e.g. an investigator-scoped view with no OOT
    # investigations still shows an "OOT" pill reading 0, rather than that
    # pill disappearing entirely.
    type_counts: Dict[str, int] = {}
    for inv in enriched:
        label = QE_TYPE_TO_STAT_LABEL.get(inv["qe_type"], inv["qe_type"] or "Unknown")
        type_counts[label] = type_counts.get(label, 0) + 1
    ordered_labels = list(_EVENT_TYPE_ORDER)
    ordered_labels += [l for l in type_counts if l not in _EVENT_TYPE_ORDER]

    # KPI cards' monthly bar chart + MoM trend — a separate query since it
    # covers the full event population (open AND closed), unlike `enriched`
    # above which is open-investigations-only (see fetch_monthly_trend_rows).
    trend_months = _month_starts(_TREND_MONTHS, datetime.date.today())
    trend_rows = [dict(r) for r in await fetch_monthly_trend_rows(trend_months[0])]
    opened_monthly = _bucket_monthly(trend_rows, "date_opened", trend_months)
    opened_trend = MonthlyTrend(monthly=opened_monthly, trend_percent=_trend_percent(opened_monthly))
    closed_trend_by_label: Dict[str, MonthlyTrend] = {}
    for label in ordered_labels:
        label_rows = [r for r in trend_rows if QE_TYPE_TO_STAT_LABEL.get(r["qe_type"], r["qe_type"] or "Unknown") == label]
        closed_monthly = _bucket_monthly(label_rows, "closed_on", trend_months)
        closed_trend_by_label[label] = MonthlyTrend(monthly=closed_monthly, trend_percent=_trend_percent(closed_monthly))

    event_type_counts = [
        EventTypeCount(
            label=label,
            count=type_counts.get(label, 0),
            percent=round(type_counts.get(label, 0) / total * 100) if total else 0,
            closed_trend=closed_trend_by_label[label],
        )
        for label in ordered_labels
    ]

    # ── Status cards (escalation-level view) ──────────────────────────
    # Unassigned and L5-L1 are INDEPENDENT dimensions, not a partition
    # (2026-09-07, per the user, correcting an earlier assumption this
    # session that they were mutually exclusive) — an investigation can be
    # both Unassigned and L1 at the same time; the escalation level has no
    # bearing on assignment status. "Unassigned" here is the same bucket
    # used everywhere else on this page (i["bucket"] == "unassigned", i.e.
    # dim_event.open_investigation_status == "Unassigned" — see _bucket_for
    # above, already used for the per-row Status pill and PendingAction.
    # is_unassigned) — NOT escalation_level being null, which was this
    # session's earlier, incorrect definition. L5-L1 remain mutually
    # exclusive among THEMSELVES (escalation_level is a single value per
    # investigation), just no longer exclusive with Unassigned.
    _ESCALATION_LEVELS = ["L5", "L4", "L3", "L2", "L1"]

    def _build_status_cards(items: List[Dict[str, Any]], show_phase_breakdown: bool = False) -> List[StatusCard]:
        unassigned = [i for i in items if i["bucket"] == "unassigned"]
        by_level = {level: [i for i in items if i.get("escalation_level") == level] for level in _ESCALATION_LEVELS}

        # Phase 1/Phase 2, as their own standalone cards alongside Unassigned
        # (SIT Dashboard Figma live prototype, 2026-09-07, per the user —
        # confirmed against the actual OOS-selected screenshot: Unassigned/
        # Phase 1/Phase 2 render as 3 sibling cards). Counted over ALL items
        # (not just the `unassigned` bucket) — same "independent dimension"
        # fix as Unassigned vs L5-L1 above: an OOS/OOT investigation's phase
        # has no bearing on its assignment status, so scoping to `unassigned`
        # first was silently hiding every already-assigned Phase 2 case
        # (confirmed live, 2026-09-07: OOS had 17 real Phase 2 investigations,
        # all already assigned, so the card read 0). Explicitly scoped by the
        # caller (only True for the OOS/OOT-labeled calls below) rather than
        # inferred from the counts — always shown when scoped to OOS/OOT,
        # even at 0/0, same "zero count still shows" convention as every
        # other card here.
        phase_cards = (
            [
                StatusCard(key="phase1", label="Phase 1", count=sum(1 for i in items if i.get("oos_oot_phase") == "Phase 1"), rows=[]),
                StatusCard(key="phase2", label="Phase 2", count=sum(1 for i in items if i.get("oos_oot_phase") == "Phase 2"), rows=[]),
            ]
            if show_phase_breakdown
            else []
        )

        return (
            [StatusCard(key="unassigned", label="Unassigned", count=len(unassigned), rows=[])]
            + phase_cards
            + [StatusCard(key=level, label=level, count=len(by_level[level]), rows=[]) for level in _ESCALATION_LEVELS]
        )

    status_cards = _build_status_cards(enriched)

    # Per the user (2026-07-31): clicking a Deviation/OOS/OOT/Market
    # Complaint pill keeps showing these SAME 4 cards (not a different
    # drill-down set) with counts filtered to just that event type — the
    # frontend picks status_cards_by_event_type[label] instead of status_cards
    # when a pill is active. Keyed by the same labels as event_type_counts.
    status_cards_by_event_type: Dict[str, List[StatusCard]] = {
        label: _build_status_cards(
            [i for i in enriched if QE_TYPE_TO_STAT_LABEL.get(i["qe_type"], i["qe_type"] or "Unknown") == label],
            show_phase_breakdown=label in ("OOS", "OOT"),
        )
        for label in ordered_labels
    }

    # ── Pending actions: fixed two-row layout (per the user, 2026-07-30) —
    # row 1 = top overdue+critical OOS, row 2 = top overdue+critical
    # Deviation (3 columns × 2 rows — see .ac-pending-grid CSS). Each row
    # prioritizes overdue+Critical first (most overdue first); if fewer than
    # _PENDING_ACTIONS_PER_ROW of those exist for that event type (per the
    # user, 2026-07-31), the remaining slots are filled with other Critical
    # rows of the same type that aren't overdue (soonest due first) rather
    # than leaving the row sparse. If slots are STILL empty after both
    # Critical tiers (2026-08-03, per the user) — i.e. there's neither an
    # overdue-Critical nor a non-overdue-Critical row left to show — the rest
    # of the row falls back to Non-Critical overdue rows of the same type
    # (most overdue first, same sort as the first tier), rather than leaving
    # the row sparse just because nothing Critical is left. Supersedes the
    # prior unified unassigned-or-overdue/criticality-first sort — this
    # panel is now scoped to exactly these two event types.
    def _urgent_critical_overdue(qe_type: str) -> List[Dict[str, Any]]:
        same_type_critical = [
            i for i in enriched if i["qe_type"] == qe_type and i["criticality"] == "Critical"
        ]
        overdue_first = [i for i in same_type_critical if i["bucket"] == "overdue"]
        overdue_first.sort(key=lambda i: i["days_until_due"] if i["days_until_due"] is not None else 9999)
        remaining = _PENDING_ACTIONS_PER_ROW - len(overdue_first)
        if remaining <= 0:
            return overdue_first[:_PENDING_ACTIONS_PER_ROW]
        fallback = [i for i in same_type_critical if i["bucket"] != "overdue"]
        fallback.sort(key=lambda i: i["days_until_due"] if i["days_until_due"] is not None else 9999)
        combined = overdue_first + fallback[:remaining]

        still_remaining = _PENDING_ACTIONS_PER_ROW - len(combined)
        if still_remaining <= 0:
            return combined
        non_critical_overdue = [
            i for i in enriched
            if i["qe_type"] == qe_type and i["criticality"] != "Critical" and i["bucket"] == "overdue"
        ]
        non_critical_overdue.sort(key=lambda i: i["days_until_due"] if i["days_until_due"] is not None else 9999)
        return combined + non_critical_overdue[:still_remaining]

    row_1_oos = _urgent_critical_overdue("Out Of Specification")
    row_2_deviation = _urgent_critical_overdue("Deviation")
    candidates = row_1_oos + row_2_deviation

    def _pending_action_text(stage: int) -> str:
        next_label = next_module_label(stage)
        if next_label == "Complete":
            return "All tracked steps are complete for this investigation."
        return f"{next_label} is the next step pending for this investigation."

    pending_actions = [
        PendingAction(
            id=i["id"],
            title=i["title"],
            due_date=_fmt_date(i["due_date"]),
            is_overdue=i["bucket"] == "overdue",
            is_unassigned=i["bucket"] == "unassigned",
            criticality=i["criticality"],
            action=_pending_action_text(i["stage"]),
            event_type=QE_TYPE_TO_STAT_LABEL.get(i["qe_type"], i["qe_type"] or "Unknown"),
        )
        for i in candidates
    ]

    # ── Progress chart: one bar per module (dim_event.module), each stacked
    # by dim_event.module_risk_status — per the backend engineer (2026-07-28).
    # Cancelled investigations aren't a real module stage and are excluded
    # entirely (see _CANCELLED_MODULE_VALUE / is_cancelled). Problem
    # Statement/Evidence Collection/Interview Questionnaire are merged into
    # one bar (_CHART_MERGED_LABEL/_CHART_MERGED_GROUP above); the old
    # always-0 "IQ Rubrics" placeholder bar is dropped entirely rather than
    # merged in.
    chart_labels = [_CHART_MERGED_LABEL] + [l for l in MODULE_LABELS if l not in _CHART_MERGED_GROUP]
    chart_counts: Dict[str, Dict[str, int]] = {
        label: {"on_track": 0, "at_risk": 0, "delayed": 0} for label in chart_labels
    }
    for inv in enriched:
        label = _MODULE_TEXT_TO_LABEL.get((inv["module"] or "").strip().lower())
        if label is None:
            continue
        if label in _CHART_MERGED_GROUP:
            label = _CHART_MERGED_LABEL
        if label not in chart_counts:
            continue
        risk_key = _MODULE_RISK_TO_KEY.get(inv["module_risk_status"], "on_track")
        chart_counts[label][risk_key] += 1
    chart = [
        ChartBar(
            label=label,
            on_track=chart_counts[label]["on_track"],
            at_risk=chart_counts[label]["at_risk"],
            delayed=chart_counts[label]["delayed"],
        )
        for label in chart_labels
    ]

    # Only one of these two sets is ever returned as `investigations` — which
    # one depends on the `status` param (2026-08-13, per the user: cancelled
    # investigations must not appear in the normal/default view at all).
    # Stat cards/chart/pending actions are computed from `enriched` alone
    # above, regardless of `status`, so they stay open-only either way — the
    # toggle only changes what the investigations table itself shows.
    if status == "cancelled":
        investigations = [
            InvestigationRow(
                id=i["id"],
                title=i["title"],
                event_type=QE_TYPE_TO_STAT_LABEL.get(i["qe_type"], i["qe_type"] or "Unknown"),
                investigator=i["investigator"],
                start_date=_fmt_date(i["date_opened"]),
                due_date=_fmt_date(i["due_date"]),
                updated_at=_fmt_date(i["updated_at"]),
                stage=0,
                total_stages=len(MODULE_LABELS),
                bucket=i["bucket"],
                site=i["site"],
                department=i["department"],
                product=i["product"],
                is_cancelled=True,
                rci_ids=i["rci_ids"],
                escalation_level=i["escalation_level"],
                oos_oot_phase=i["oos_oot_phase"],
            )
            for i in cancelled_enriched
        ]
    else:
        investigations = [
            InvestigationRow(
                id=i["id"],
                title=i["title"],
                event_type=QE_TYPE_TO_STAT_LABEL.get(i["qe_type"], i["qe_type"] or "Unknown"),
                investigator=i["investigator"],
                start_date=_fmt_date(i["date_opened"]),
                due_date=_fmt_date(i["due_date"]),
                updated_at=_fmt_date(i["updated_at"]),
                stage=i["stage"],
                total_stages=len(MODULE_LABELS),
                bucket=i["bucket"],
                site=i["site"],
                department=i["department"],
                product=i["product"],
                is_cancelled=i["is_cancelled"],
                rci_ids=i["rci_ids"],
                escalation_level=i["escalation_level"],
                oos_oot_phase=i["oos_oot_phase"],
            )
            for i in enriched
        ]

    return ActionCenterSummary(
        total_investigations=total,
        event_type_counts=event_type_counts,
        opened_trend=opened_trend,
        status_cards=status_cards,
        status_cards_by_event_type=status_cards_by_event_type,
        pending_actions=pending_actions,
        chart=chart,
        investigations=investigations,
        filter_options=filter_options,
    )
