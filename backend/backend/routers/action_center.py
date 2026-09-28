from __future__ import annotations

import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.db.action_center_queries import (
    QE_TYPE_TO_STAT_LABEL,
    fetch_all_departments,
    fetch_cancelled_investigations,
    fetch_investigator_progress_stage,
    fetch_monthly_trend_rows,
    fetch_open_investigations,
)
from backend.db.generated_content_queries import fetch_remarks, save_remark
from backend.db.module_stage import MODULE_LABELS, next_module_label, stage_for
from backend.routers.auth import get_current_payload, require_sit
from backend.schemas.action_center import (
    ActionCenterSummary,
    ChartBar,
    EventTypeCount,
    FilterOptions,
    InvestigationRow,
    MonthlyBar,
    MonthlyTrend,
    PendingAction,
    RemarkUpdateRequest,
    StatusCard,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/action-center", tags=["Action Center"])

_PENDING_ACTIONS_PER_ROW = 3

_EVENT_TYPE_ORDER = ["Deviation", "OOS", "OOT", "Market Complaint"]

# 6 bars: the current (in-progress) month plus the 5 before it — not just fully completed months.
_TREND_MONTHS = 6


def _month_starts(n: int, today: datetime.date) -> List[datetime.date]:
    """n calendar month-start dates, oldest first, including the current (possibly partial) month."""
    months = []
    cursor = today.replace(day=1)
    for _ in range(n):
        months.append(cursor)
        cursor = (cursor - datetime.timedelta(days=1)).replace(day=1)
    return list(reversed(months))


def _bucket_monthly(rows: List[Dict[str, Any]], date_key: str, months: List[datetime.date]) -> List[MonthlyBar]:
    counts = {m: 0 for m in months}
    for row in rows:
        d = row.get(date_key)
        if d is None:
            continue
        # TIMESTAMPs need .date() first, or they'd never equal the plain `date` keys in
        # `counts`, silently zeroing every bucket.
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

# Sentinel meaning "no investigator assigned", sent/received as a plain investigator= value.
_UNASSIGNED_INVESTIGATOR_FILTER = "__unassigned__"

# Chart-only grouping: these three merge into one stacked-label bar. MODULE_LABELS itself stays
# untouched — it still drives stage_for()/next_module_label() and the "X/6 steps" fraction.
_CHART_MERGED_GROUP = ["Problem Statement", "Evidence Collection", "Interview Questionnaire"]
_CHART_MERGED_LABEL = "\n".join(_CHART_MERGED_GROUP)

# Maps dim_event.module to chart labels, matched case/whitespace-insensitively since the text has drifted between an older lowercase form and a newer Title Case one; "RC & CAPA Critique" -> "Task Critique" is a chart-only grouping, a separate module everywhere else.
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

# Cancelled investigations aren't a real module stage — excluded from the progress chart and
# shown as a "Cancelled" pill instead of a progress bar in the table.
_CANCELLED_MODULE_VALUE = "Cancelled"

# module_risk_status -> which of the chart's 3 stacked series a row counts toward. "Unknown" has
# no series, but only ever co-occurs with module=None, which is already excluded from the chart.
_MODULE_RISK_TO_KEY: Dict[str, str] = {
    "Closed": "on_track",
    "At Risk": "at_risk",
    "Delayed": "delayed",
}

# open_investigation_status -> the dashboard's internal bucket key.
_OPEN_STATUS_TO_BUCKET: Dict[str, str] = {
    "Unassigned": "unassigned",
    "On Track": "on_track",
    "At Risk": "delay",
    "Overdue": "overdue",
}


def _fmt_date(d: Optional[datetime.date]) -> Optional[str]:
    return d.strftime("%d %b %Y") if d else None


# due_date_display is the upstream-resolved due-date text ("MM/DD/YYYY", or "MM/DD/YYYY(EXT)"
# when extended) — shown as-is (reformatted), no picking between due_date/extended_due_date here.
def _fmt_due_date_display(due_date_display: Optional[str]) -> Optional[str]:
    if not due_date_display:
        return None
    is_extended = due_date_display.endswith("(EXT)")
    date_part = due_date_display[: -len("(EXT)")] if is_extended else due_date_display
    parsed = datetime.datetime.strptime(date_part, "%m/%d/%Y").date()
    formatted = _fmt_date(parsed)
    return f"{formatted} (EXT)" if is_extended else formatted


def _bucket_for(open_investigation_status: Optional[str]) -> str:
    return _OPEN_STATUS_TO_BUCKET.get(open_investigation_status, "unassigned")


# investigator_by_rci is jsonb; asyncpg returns it as a raw JSON string (no codec on this pool),
# not a dict, and None when no fact_qms_event row for this deviation has a non-null rci_key.
def _parse_investigator_by_rci(raw: Optional[str]) -> Dict[str, str]:
    if not raw:
        return {}
    return json.loads(raw)


# STOPGAP: product_key=620 is the ETL's unresolved-product catch-all (~14% of rows) — until fixed upstream, fall back to parsing the product out of dim_event.title (format differs by event type; Deviation titles aren't handled).
_MC_TITLE_PRODUCT_RE = re.compile(r"^(.*?)[;,]\s*B\.?\s*N\.?(?:o\.?)?\b", re.IGNORECASE)
_OOS_OOT_BATCH_ANCHOR_RE = re.compile(r"(?:B\.?\s*N\.?(?:o\.?)?|for\s+batch)\s*[:\-]?\s*\S+(.*)$", re.IGNORECASE)
# Strips stability-study shorthand ("06M", "ASL") sitting before the product name with no delimiter.
_LEADING_STUDY_CODE_RE = re.compile(r"^(?:ASL|\d{1,3}M)\s+")


def _extract_product_from_title(title: Optional[str], qe_type_label: str) -> Optional[str]:
    if not title:
        return None
    if qe_type_label == "Market Complaint":
        m = _MC_TITLE_PRODUCT_RE.match(title)
        candidate = m.group(1).strip(" -") if m else None
        return candidate or None
    if qe_type_label in ("OOS", "OOT"):
        m = _OOS_OOT_BATCH_ANCHOR_RE.search(title)
        if not m:
            return None
        # The product segment is reliably the longest dash/comma-separated part — "last segment"
        # can instead grab a trailing site/country code.
        parts = [p.strip() for p in re.split(r"[-,]", m.group(1)) if p.strip()]
        if not parts:
            return None
        candidate = max(parts, key=len)
        candidate = _LEADING_STUDY_CODE_RE.sub("", candidate)
        return candidate or None
    return None


def _resolve_product(raw_product: Optional[str], title: Optional[str], qe_type_label: str) -> Optional[str]:
    if raw_product and raw_product != "Not Applicable":
        return raw_product
    return _extract_product_from_title(title, qe_type_label) or raw_product


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
    claims: dict = Depends(get_current_payload),
) -> ActionCenterSummary:
    rows = await fetch_open_investigations()
    cancelled_rows = await fetch_cancelled_investigations()
    all_departments = await fetch_all_departments()

    # pg_updated_at_timestamp is a naive TIMESTAMP; without tzinfo attached, a JS Date parses it as the browser's own local time instead of UTC, breaking the frontend's IST conversion for non-IST viewers.
    last_updated_at_raw = next(
        (r["pg_updated_at_timestamp"] for r in (*rows, *cancelled_rows) if r["pg_updated_at_timestamp"]), None
    )
    last_updated_at = last_updated_at_raw.replace(tzinfo=datetime.timezone.utc) if last_updated_at_raw else None

    # Investigator-role scoping — filtered before any aggregation, so every derived number (KPI
    # counts, status cards, pills, pending actions, table) is scoped, not just the table.
    #
    # A deviation with two RCIs opened simultaneously (2026-09-25, per the user — the OOS/OOT
    # "Phase 2" scenario) can have a DIFFERENT investigator on each RCI. The row-level `investigator`
    # field is only ever the single winning row from _OPEN_INVESTIGATIONS_QUERY's dedup (highest
    # rci_key) — so filtering on that field alone silently hid the whole deviation from whichever
    # investigator's RCI didn't win the dedup, even though investigator_by_rci already has the
    # correct per-RCI breakdown. scoped_rci_ids records, per surviving deviation_id, exactly which
    # of its rci_ids belong to this investigator, so the enrichment loop below can trim rci_ids/
    # investigator_by_rci/remarks/investigator_stage_by_rci down to just their own RCI(s) too —
    # an investigator must not see a colleague's RCI on the same deviation.
    own_investigator: Optional[str] = None
    scoped_rci_ids: Dict[int, List[str]] = {}
    if "Investigator" in (claims.get("roles") or []):
        own_investigator = (claims.get("investigator_name") or claims.get("name") or "").strip()
        own_investigator_ci = own_investigator.lower()

        def _own_rci_ids(r: Any) -> List[str]:
            by_rci = _parse_investigator_by_rci(r["investigator_by_rci"])
            matches = [rid for rid, name in by_rci.items() if (name or "").strip().lower() == own_investigator_ci]
            if matches:
                return matches
            # No per-rci_id investigator breakdown at all (deviation has no rci_key yet) — fall
            # back to the row's own single deduped investigator field, matching this case's only
            # historical behavior (a deviation with 0 RCIs still needs a match to show at all).
            if not by_rci and (r["investigator"] or "").strip().lower() == own_investigator_ci:
                return list(r["rci_ids"]) if r["rci_ids"] else []
            return []

        def _filter_and_scope(candidates: List[Any]) -> List[Any]:
            kept = []
            for r in candidates:
                matches = _own_rci_ids(r)
                if matches:
                    scoped_rci_ids[r["deviation_id"]] = matches
                    kept.append(r)
            return kept

        rows = _filter_and_scope(rows)
        cancelled_rows = _filter_and_scope(cancelled_rows)

    # Remark column: visible (read-only) to every role, editable by SIT only (enforced by
    # require_sit on the PUT endpoint below, and by the frontend's readOnly textarea).
    all_deviation_ids = [r["deviation_id"] for r in (*rows, *cancelled_rows)]
    remarks_by_deviation: Dict[int, Dict[str, str]] = await fetch_remarks(all_deviation_ids)

    # Open investigations only — cancelled rows hardcode investigator_stage=0 below, same as they
    # already do for `stage`.
    investigator_stage_by_deviation = await fetch_investigator_progress_stage([r["deviation_id"] for r in rows])

    today = datetime.date.today()

    enriched: List[Dict[str, Any]] = []
    for r in rows:
        due_date_display = _fmt_due_date_display(r["due_date_display"])
        # Must use the extension when set, matching the upstream escalation bucket, or
        # days_until_due would disagree with a row's own Overdue/At Risk status.
        effective_due_date = (r["extended_due_date"] or r["due_date"])
        effective_due_date = effective_due_date.date() if effective_due_date else None
        date_opened = r["date_opened"].date() if r["date_opened"] else None
        # CAVEAT (unresolved): pg_updated_at_timestamp is one flat bulk-load stamp shared by
        # every row, not a real per-investigation "last updated" signal.
        updated_at = r["pg_updated_at_timestamp"].date() if r["pg_updated_at_timestamp"] else None
        days_until_due = (effective_due_date - today).days if effective_due_date else None
        days_since_opened = (today - date_opened).days if date_opened else 0
        # stage: TrackWise's own module/state (module_stage.stage_for) — still drives Pending
        # Actions and is exposed as the secondary toggled-on column; _MODULE_TEXT_TO_LABEL below is
        # for the chart only. investigator_stage: the table's PRIMARY progress bar (see
        # fetch_investigator_progress_stage's docstring for its "last item, Investigator role only"
        # semantics) — a deliberately separate signal, not derived from `stage`.
        stage = stage_for(r["module"])
        investigator_stage_by_rci = investigator_stage_by_deviation.get(r["deviation_id"], {})
        # Backward-compat scalar: the "" (no-rci) entry if present, else whichever single rci's
        # stage is available (today's non-multi-RCI rows), else 0.
        investigator_stage = investigator_stage_by_rci.get(
            "", next(iter(investigator_stage_by_rci.values()), 0)
        )
        row_investigator_by_rci = _parse_investigator_by_rci(r["investigator_by_rci"])
        row_rci_ids = list(r["rci_ids"]) if r["rci_ids"] else []
        # Investigator role: trim every per-RCI view down to just the RCI(s) actually assigned to
        # this investigator — they must not see a colleague's RCI on the same deviation (see the
        # scoped_rci_ids comment above). Other roles (SIT/Admin) see the full unscoped breakdown.
        row_investigator = r["investigator"]
        if r["deviation_id"] in scoped_rci_ids:
            own_ids = scoped_rci_ids[r["deviation_id"]]
            row_rci_ids = [rid for rid in row_rci_ids if rid in own_ids] or own_ids
            row_investigator_by_rci = {rid: name for rid, name in row_investigator_by_rci.items() if rid in own_ids}
            investigator_stage_by_rci = {rid: v for rid, v in investigator_stage_by_rci.items() if rid in own_ids}
            # Reflects the investigator actually looking at this row, not whichever RCI happened
            # to win the dedup — matches row_investigator_by_rci[own_ids[0]] when available.
            row_investigator = row_investigator_by_rci.get(own_ids[0], own_investigator) if own_ids else row_investigator
            investigator_stage = investigator_stage_by_rci.get("", next(iter(investigator_stage_by_rci.values()), 0))
        enriched.append(
            {
                "id": str(r["deviation_id"]),
                "title": r["title"] or "Untitled Investigation",
                "qe_type": r["qe_type"],
                "investigator": row_investigator,
                "site": r["location"],
                "department": r["department"],
                "product": _resolve_product(
                    r["product"], r["title"], QE_TYPE_TO_STAT_LABEL.get(r["qe_type"], r["qe_type"] or "Unknown")
                ),
                "criticality": r["criticality"],
                "event_classification": r["event_classification"],
                "oos_oot_phase": r["oos_oot_phase"],
                "escalation_level": r["escalation_level"],
                "due_date_display": due_date_display,
                "date_opened": date_opened,
                "updated_at": updated_at,
                "days_until_due": days_until_due,
                "days_since_opened": days_since_opened,
                "stage": stage,
                "investigator_stage": investigator_stage,
                "investigator_stage_by_rci": investigator_stage_by_rci,
                "bucket": _bucket_for(r["open_investigation_status"]),
                "module": r["module"],
                "module_risk_status": r["module_risk_status"],
                "is_cancelled": r["module"] == _CANCELLED_MODULE_VALUE,
                "rci_ids": row_rci_ids,
                "remarks": {
                    rci_id: remark
                    for rci_id, remark in remarks_by_deviation.get(r["deviation_id"], {}).items()
                    if r["deviation_id"] not in scoped_rci_ids or rci_id in scoped_rci_ids[r["deviation_id"]]
                },
                "investigator_by_rci": row_investigator_by_rci,
            }
        )

    # Cancelled investigations are kept out of `enriched` (must not affect totals/pills/cards/
    # chart) and instead shown in the table after every open investigation, ordered by deviation_id.
    cancelled_enriched: List[Dict[str, Any]] = []
    for r in cancelled_rows:
        due_date_display = _fmt_due_date_display(r["due_date_display"])
        date_opened = r["date_opened"].date() if r["date_opened"] else None
        updated_at = r["pg_updated_at_timestamp"].date() if r["pg_updated_at_timestamp"] else None  # see caveat above
        row_investigator_by_rci = _parse_investigator_by_rci(r["investigator_by_rci"])
        row_rci_ids = list(r["rci_ids"]) if r["rci_ids"] else []
        row_investigator = r["investigator"]
        if r["deviation_id"] in scoped_rci_ids:
            own_ids = scoped_rci_ids[r["deviation_id"]]
            row_rci_ids = [rid for rid in row_rci_ids if rid in own_ids] or own_ids
            row_investigator_by_rci = {rid: name for rid, name in row_investigator_by_rci.items() if rid in own_ids}
            row_investigator = row_investigator_by_rci.get(own_ids[0], own_investigator) if own_ids else row_investigator
        cancelled_enriched.append(
            {
                "deviation_id": r["deviation_id"],
                "id": str(r["deviation_id"]),
                "title": r["title"] or "Untitled Investigation",
                "qe_type": r["qe_type"],
                "investigator": row_investigator,
                "site": r["location"],
                "department": r["department"],
                "product": _resolve_product(
                    r["product"], r["title"], QE_TYPE_TO_STAT_LABEL.get(r["qe_type"], r["qe_type"] or "Unknown")
                ),
                "criticality": r["criticality"],
                "event_classification": r["event_classification"],
                "oos_oot_phase": r["oos_oot_phase"],
                "escalation_level": r["escalation_level"],
                "due_date_display": due_date_display,
                "date_opened": date_opened,
                "updated_at": updated_at,
                "bucket": _bucket_for(r["open_investigation_status"]),
                "rci_ids": row_rci_ids,
                "remarks": {
                    rci_id: remark
                    for rci_id, remark in remarks_by_deviation.get(r["deviation_id"], {}).items()
                    if r["deviation_id"] not in scoped_rci_ids or rci_id in scoped_rci_ids[r["deviation_id"]]
                },
                "investigator_by_rci": row_investigator_by_rci,
            }
        )

    # Sort by date_opened, newest first, so switching between overlapping filters doesn't
    # reshuffle rows unpredictably; rows with no date_opened sort last.
    with_date = [i for i in enriched if i["date_opened"] is not None]
    without_date = [i for i in enriched if i["date_opened"] is None]
    with_date.sort(key=lambda i: i["date_opened"], reverse=True)
    enriched = with_date + without_date

    # Site/department/product dropdowns reflect the full open set; the investigator dropdown is scoped to the OTHER active filters, computed before the investigator filter narrows `enriched` below.
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
    # "Unassigned" only appears when at least one row in the current view actually has none.
    if any(not i["investigator"] for i in scoped_for_investigator_options):
        investigator_options = [_UNASSIGNED_INVESTIGATOR_FILTER] + investigator_options

    filter_options = FilterOptions(
        sites=sorted({i["site"] for i in enriched if i["site"]}),
        # Static full list — unlike sites/products/investigators, not scoped to what's currently open.
        departments=all_departments,
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

    # Same filters applied to cancelled investigations, then ordered by deviation_id; this list
    # gets appended after `enriched` further down, always landing on the last page(s).
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

    # ── Event type breakdown ── fixed display order (not by count); all 4 always show, even at 0.
    type_counts: Dict[str, int] = {}
    for inv in enriched:
        label = QE_TYPE_TO_STAT_LABEL.get(inv["qe_type"], inv["qe_type"] or "Unknown")
        type_counts[label] = type_counts.get(label, 0) + 1
    ordered_labels = list(_EVENT_TYPE_ORDER)
    ordered_labels += [l for l in type_counts if l not in _EVENT_TYPE_ORDER]

    # Separate query since it covers open AND closed events. Falls back to the `investigator`
    # filter param since own_investigator is only set for the real Investigator role, not "View as Investigator".
    trend_investigator = own_investigator or (
        investigator if investigator and investigator != _UNASSIGNED_INVESTIGATOR_FILTER else None
    )
    trend_months = _month_starts(_TREND_MONTHS, datetime.date.today())
    trend_rows = [dict(r) for r in await fetch_monthly_trend_rows(trend_months[0], trend_investigator)]
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
            percent=round(type_counts.get(label, 0) / total * 100, 1) if total else 0,
            closed_trend=closed_trend_by_label[label],
        )
        for label in ordered_labels
    ]

    # ── Status cards ── Unassigned and L5-L1 are independent dimensions, not a partition: an investigation can be both Unassigned and L1 at once.
    _ESCALATION_LEVELS = ["L5", "L4", "L3", "L2", "L1"]

    def _build_status_cards(items: List[Dict[str, Any]], show_phase_breakdown: bool = False) -> List[StatusCard]:
        unassigned = [i for i in items if i["bucket"] == "unassigned"]
        by_level = {level: [i for i in items if i.get("escalation_level") == level] for level in _ESCALATION_LEVELS}

        # Phase 1/2 counted over ALL items, not just `unassigned` — scoping to unassigned first hid already-assigned Phase 2 cases.
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

    # Clicking an event-type pill keeps showing these same cards, filtered to that type — the
    # frontend picks status_cards_by_event_type[label] instead of status_cards when active.
    status_cards_by_event_type: Dict[str, List[StatusCard]] = {
        label: _build_status_cards(
            [i for i in enriched if QE_TYPE_TO_STAT_LABEL.get(i["qe_type"], i["qe_type"] or "Unknown") == label],
            show_phase_breakdown=label in ("OOS", "OOT"),
        )
        for label in ordered_labels
    }

    # ── Pending actions: row 1 = top OOS, row 2 = top Deviation; priority is overdue+Critical, then non-overdue Critical, then Non-Critical overdue as a last-resort fill.
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
            due_date=i["due_date_display"],
            is_overdue=i["bucket"] == "overdue",
            is_unassigned=i["bucket"] == "unassigned",
            criticality=i["criticality"],
            action=_pending_action_text(i["stage"]),
            event_type=QE_TYPE_TO_STAT_LABEL.get(i["qe_type"], i["qe_type"] or "Unknown"),
        )
        for i in candidates
    ]

    # ── Progress chart: one bar per module, stacked by module_risk_status; cancelled investigations excluded, the old always-0 "IQ Rubrics" bar dropped entirely.
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

    # Only one of these two sets is returned as `investigations`, chosen by `status`; stat
    # cards/chart/pending actions stay open-only either way — the toggle only affects the table.
    if status == "cancelled":
        investigations = [
            InvestigationRow(
                id=i["id"],
                title=i["title"],
                event_type=QE_TYPE_TO_STAT_LABEL.get(i["qe_type"], i["qe_type"] or "Unknown"),
                investigator=i["investigator"],
                start_date=_fmt_date(i["date_opened"]),
                due_date=i["due_date_display"],
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
                criticality=i["criticality"],
                event_classification=i["event_classification"],
                remarks=i["remarks"],
                investigator_by_rci=i["investigator_by_rci"],
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
                due_date=i["due_date_display"],
                updated_at=_fmt_date(i["updated_at"]),
                stage=i["stage"],
                investigator_stage=i["investigator_stage"],
                investigator_stage_by_rci=i["investigator_stage_by_rci"],
                total_stages=len(MODULE_LABELS),
                bucket=i["bucket"],
                site=i["site"],
                department=i["department"],
                product=i["product"],
                is_cancelled=i["is_cancelled"],
                rci_ids=i["rci_ids"],
                escalation_level=i["escalation_level"],
                oos_oot_phase=i["oos_oot_phase"],
                criticality=i["criticality"],
                event_classification=i["event_classification"],
                remarks=i["remarks"],
                investigator_by_rci=i["investigator_by_rci"],
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
        last_updated_at=last_updated_at,
    )


@router.put("/{record_id}/remark")
async def update_investigation_remark(
    record_id: str,
    request: RemarkUpdateRequest,
    _: str = Depends(require_sit),
) -> Dict[str, str]:
    """SIT Dashboard's "Remark" column, editable by SIT only (enforced via require_sit). Keyed
    by (record_id, rci_id), not record_id alone, since a deviation with multiple RCI IDs renders
    as multiple rows, each needing its own remark; rci_id is "" for a row with none."""
    try:
        deviation_id = int(record_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No investigation found for this record")

    await save_remark(deviation_id, request.rci_id, request.remark)
    return {"remark": request.remark}
