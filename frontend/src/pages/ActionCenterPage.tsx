import { useEffect, useState } from "react";
import { StatusChart } from "../components/StatusChart";
import { InvestigationPreviewPanel, type PreviewInvestigation } from "../components/InvestigationPreviewPanel";
import { DbErrorModal } from "../components/DbErrorModal";
import { FilterSelect } from "../components/FilterSelect";
import { InfoTooltip } from "../components/InfoTooltip";
import { CriticalityGuidelines } from "../components/CriticalityGuidelines";
import { formatSiteLabel } from "../constants/siteLabels";
import { ApiError } from "../api/client";
import { getActionCenterSummary, type ActionCenterSummaryResponse, type InvestigationRowResponse, type MonthlyTrend, type StatusCardResponse } from "../api/dashboard";
import { useAuth } from "../auth/AuthContext";
import iconUnassigned from "../assets/icons/status-unassigned.svg";
import iconSearch from "../assets/icons/search.svg";
import iconViewGrid from "../assets/icons/view-grid.png";
import iconViewList from "../assets/icons/view-list.png";
import iconRowArrow from "../assets/icons/row-arrow.svg";
import "./ActionCenterPage.css";

// Only "Unassigned" has an icon (matches the SIT Dashboard Figma — the L1-L5
// cards show no icon, just the level text). renderStatusCard skips the <img>
// when a card's key has no entry here.
const STATUS_ICONS: Record<string, string> = {
  unassigned: iconUnassigned,
};

// Status cards are keyed by dim_event.escalation_level ("L1".."L5") or
// "unassigned"/"phase1"/"phase2" (see action_center.py's _build_status_cards).
// Unassigned and L5-L1 are INDEPENDENT dimensions, not a partition
// (2026-09-07, per the user, correcting an earlier assumption this session
// that they were mutually exclusive) — an investigation can be both
// Unassigned and L1 at once, so this does NOT derive "unassigned" from a
// missing escalation_level; it uses the same `bucket` field as the per-row
// Status pill/PendingAction.is_unassigned everywhere else on this page.
function matchesStatusCard(inv: InvestigationRowResponse, cardKey: string): boolean {
  // Phase 1/Phase 2 are their own standalone cards, independent of
  // assignment status (2026-09-07, per the user) — an OOS/OOT
  // investigation's phase has no bearing on whether it's unassigned, only
  // ever present when scoped to OOS/OOT (see action_center.py's
  // show_phase_breakdown).
  if (cardKey === "phase1") return inv.oos_oot_phase === "Phase 1";
  if (cardKey === "phase2") return inv.oos_oot_phase === "Phase 2";
  if (cardKey === "unassigned") return inv.bucket === "unassigned";
  return inv.escalation_level === cardKey;
}

// Real backend bucket -> the table/grid status-pill styling + label.
const BUCKET_TO_STATUS: Record<string, { status: string; label: string }> = {
  unassigned: { status: "unassigned", label: "Unassigned" },
  delay: { status: "due-soon", label: "At Risk of Delay" },
  on_track: { status: "in-progress", label: "In Progress" },
  overdue: { status: "overdue", label: "Overdue" },
};

// dim_event.escalation_level ("L1".."L5", or "Not Applicable"/null for most
// rows) -> the same 5 distinct tones as the escalation-level status cards
// above (2026-09-04, per the user — previously grouped into just
// success/warning/danger, now one tone per level to match).
const ESCALATION_TONE: Record<string, "success" | "info" | "warning" | "pink" | "danger"> = {
  L1: "success",
  L2: "info",
  L3: "warning",
  L4: "pink",
  L5: "danger",
};

// Default table order (before the user picks a column to sort by): most
// overdue first (2026-08-21, per the user). Sorting by bucket rather than
// raw due_date, since open_investigation_status is Trackwise's own opaque
// determination — not always strictly derivable from due_date alone (see
// project memory on overdue/delay/on-track logic) — so an explicit bucket
// isn't guaranteed to line up with a plain due_date sort. Within the same
// bucket, earliest due date (most overdue, or soonest due) sorts first.
const DEFAULT_SORT_BUCKET_PRIORITY: Record<string, number> = {
  overdue: 0,
  delay: 1,
  on_track: 2,
  unassigned: 3,
};


// Matches the backend's _UNASSIGNED_INVESTIGATOR_FILTER sentinel exactly —
// sent/received as a plain investigator= value, same as a real name, just
// matched server-side against a null/blank investigator instead of an
// equality check. Only appears in filter_options.investigators when at
// least one investigation in view actually has none.
const UNASSIGNED_INVESTIGATOR_FILTER = "__unassigned__";

function formatInvestigatorLabel(investigator: string): string {
  return investigator === UNASSIGNED_INVESTIGATOR_FILTER ? "Unassigned" : investigator;
}

// Every Investigation Details column except "Investigation" itself is
// sortable — this list drives both the clickable headers and the sort logic.
type SortColumn = "product" | "investigator" | "progress" | "start_date" | "due_date" | "status";

const SORTABLE_COLUMNS: { key: SortColumn; label: string }[] = [
  { key: "product", label: "Product" },
  { key: "investigator", label: "Investigator" },
  { key: "progress", label: "Progress" },
  { key: "start_date", label: "Start Date" },
  { key: "due_date", label: "Due Date" },
  { key: "status", label: "Status" },
];

// start_date/due_date are pre-formatted display strings ("29 Jul 2026"), not
// ISO — plain string comparison would sort by month name alphabetically
// (Apr, Aug, Dec, Feb...), so parse to a timestamp for real chronological
// sorting instead.
function parseDisplayDateMs(value: string | null): number | null {
  if (!value) return null;
  const ms = new Date(value).getTime();
  return Number.isNaN(ms) ? null : ms;
}

function getSortValue(inv: InvestigationRowResponse, column: SortColumn): string | number | null {
  switch (column) {
    case "product":
      return inv.product;
    case "investigator":
      return inv.investigator;
    case "progress":
      return inv.total_stages ? inv.stage / inv.total_stages : 0;
    case "start_date":
      return parseDisplayDateMs(inv.start_date);
    case "due_date":
      return parseDisplayDateMs(inv.due_date);
    case "status":
      return inv.is_cancelled ? "Cancelled" : (BUCKET_TO_STATUS[inv.bucket] ?? BUCKET_TO_STATUS.unassigned).label;
  }
}

// Nulls (no investigator/date yet) always sort to the end regardless of
// direction — flipping them with the rest of the comparison on "desc" would
// put blanks first, which reads as broken rather than sorted.
function compareForSort(a: string | number | null, b: string | number | null, direction: "asc" | "desc"): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  const cmp = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));
  return direction === "asc" ? cmp : -cmp;
}

// KPI card mini bar-chart tone is driven by the MoM trend direction
// (2026-09-07, per the user) — red when the trend is negative, green when
// positive, grey when exactly 0 or undefined (previous month's count was
// 0, so a % change isn't meaningful) — reusing the existing "warm"
// (red)/"cool" (green)/"neutral" (grey) chart-color families rather than
// introducing new tokens, since those already are red/green/grey.
function trendTone(trendPercent: number | null): "neutral" | "warm" | "cool" {
  if (!trendPercent) return "neutral";
  return trendPercent < 0 ? "warm" : "cool";
}

// Left-edge accent color per event-type KPI card (SIT Dashboard Figma,
// 2026-09-08, per the user) — static per event type, not tied to MoM trend
// direction (unlike the mini bar chart's own coloring above). OOS got its
// own deep-purple color (2026-09-08, per the user), split out of the blue
// group it originally shared with Deviation.
function eventTypeAccentClass(label: string): "event-blue" | "event-teal" | "event-purple" {
  if (label === "OOS") return "event-purple";
  return label === "Deviation" ? "event-blue" : "event-teal";
}

// Fixed pixel height of .ac-kpi-chart in ActionCenterPage.css — bar heights
// are computed in JS as a pixel value against this, not a CSS `%`, since a
// percentage height on a flex item only resolves reliably when every
// ancestor in the chain has its own definite (non-flex-computed) height;
// through .ac-kpi-bar-col/.ac-kpi-chart's flex layout it didn't, so every
// bar silently fell back to the same rendered height regardless of count
// (confirmed live, 2026-09-04, per the user).
const KPI_CHART_HEIGHT_PX = 40;

// Rounds a chart's max count up to a "nice" axis ceiling built from ~4
// steps of a round size (the classic 1-2-5-10 sequence) — e.g. a max of 75
// picks a step of 20 for a 0-20-40-60-80 scale; a max of 101 picks a step
// of 50 for 0-50-100-150 (2026-09-04, per the user). Keeps bars
// proportional to a real 0 baseline (went back on an earlier min-max
// version, which exaggerated differences but made bar height no longer
// mean the real number) while still giving the tallest bar some headroom
// instead of always touching the top.
function niceAxisMax(max: number, targetSteps = 4): number {
  if (max <= 0) return 1;
  const rawStep = max / targetSteps;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
  return Math.ceil(max / step) * step;
}

// Renders a MonthlyTrend as a small bar chart (older months "muted", the
// most recent "strong") with month labels beneath, plus a caption + MoM
// trend line below that — e.g. "Opened / month  ▼ 9% MoM". Tone (red/
// green/grey) is derived from the trend direction by default; pass
// forceTone="neutral" to opt out (2026-09-07, per the user — Open
// Investigations' own chart stays grey regardless of trend direction).
// invertTrendColor swaps which arrow direction reads as good/bad (2026-09-08,
// per the user) — every other card tracks "Closed / month", where more is
// good (▲ green); Open Investigations tracks "Opened / month", where more
// is bad, so ▲ should read red and ▼ green there instead.
function renderKpiChart(trend: MonthlyTrend, caption: string, forceTone?: "neutral", invertTrendColor = false) {
  const tone = forceTone ?? trendTone(trend.trend_percent);
  const axisMax = niceAxisMax(Math.max(...trend.monthly.map((b) => b.count)));
  const heightFor = (count: number) => Math.max(2, Math.round((count / axisMax) * KPI_CHART_HEIGHT_PX));
  const isDown = trend.trend_percent !== null && trend.trend_percent < 0;
  const isUp = trend.trend_percent !== null && trend.trend_percent > 0;
  const trendClass = isDown ? (invertTrendColor ? "up" : "down") : isUp ? (invertTrendColor ? "down" : "up") : "";
  return (
    <>
      <div className={`ac-kpi-chart ac-kpi-chart-${tone}`}>
        {trend.monthly.map((bar, i) => (
          <div className="ac-kpi-bar-col" key={bar.label + i}>
            <span className="ac-kpi-bar-tooltip">{bar.count}</span>
            <div
              className={`ac-kpi-bar ${i === trend.monthly.length - 1 ? "strong" : "muted"}`}
              style={{ height: heightFor(bar.count) }}
            />
            <span className="ac-kpi-bar-label">{bar.label}</span>
          </div>
        ))}
      </div>
      <div className="ac-kpi-trend">
        <span>{caption}</span>
        {trend.trend_percent !== null && (
          <span className={trendClass}>
            {isDown ? "▼" : isUp ? "▲" : "—"} {Math.abs(trend.trend_percent)}% from last month
          </span>
        )}
      </div>
    </>
  );
}

// Supervisor variant of the Action Center (see project memory: Action Center
// has CXO/Supervisor/Investigator variants — CXO is on hold, Investigator
// filters this same data down to the current user). Real data as of
// 2026-07-24, sourced from GET /action-center/summary — see project memory:
// action_center_roles for the business-rule placeholders this endpoint
// encodes (status buckets, pending actions, progress chart).

// Per-level tagline (SIT Dashboard Figma, 2026-09-04/08, per the user) — the
// days-open range each escalation level represents, copied verbatim from
// the Figma mock. Market Complaint gets its own, more lenient set (2026-09-08,
// per the user, confirmed against a Market-Complaint-scoped screenshot) —
// consistent with this page's own due-date InfoTooltip elsewhere, which
// already documents a 55-day window for Market Complaints vs 30 days for
// Deviation/OOS/OOT. Frontend-only static text: dim_event.escalation_level
// is computed upstream by TrackWise, not derived here, so these ranges
// aren't independently verified against a real threshold in this codebase —
// they document what the design shows, not a rule this app enforces.
const LEVEL_CAPTION_DEFAULT: Record<string, string> = {
  L5: "Days Open > 30",
  L4: "26 ≤ Days Open ≤ 30",
  L3: "21 ≤ Days Open ≤ 25",
  L2: "16 ≤ Days Open ≤ 20",
  L1: "Days Open ≤ 15",
};
const LEVEL_CAPTION_MARKET_COMPLAINT: Record<string, string> = {
  L5: "Days Open > 55",
  L4: "51 ≤ Days Open ≤ 55",
  L3: "41 ≤ Days Open ≤ 50",
  L2: "31 ≤ Days Open ≤ 40",
  L1: "Days Open ≤ 30",
};

const ASSIGNMENT_FILTER_OPTIONS: { key: "all" | "assigned" | "unassigned"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "assigned", label: "Assigned" },
  { key: "unassigned", label: "Unassigned" },
];

// Replaces the plain "Unassigned" card for Deviation/Market Complaint/no
// filter (2026-09-08, per the user) — 3 vertically-stacked radio buttons,
// always exactly one selected, filtering by inv.bucket === "unassigned"
// independently of the L5-L1 level filter (see assignmentFilter's own
// comment at its declaration). Styled to match the other status cards in
// the same row (.ac-status-card/.ac-status-card-header) so it doesn't look
// like a foreign control dropped into the row.
function renderAssignmentFilterCard(value: "all" | "assigned" | "unassigned", onChange: (v: "all" | "assigned" | "unassigned") => void) {
  return (
    <div className="ac-status-card unassigned" key="assignment-filter">
      <div className="ac-status-card-header">
        <span>Status</span>
      </div>
      <div style={{ padding: "0 20px 20px" }}>
        {/* Single segmented pill, not 3 separate radio rows (2026-09-08,
            per the user) — same .ac-criticality-toggle look as the "All /
            Critical / Major-Minor" control in the filter bar above, for
            visual consistency. The "stretch" modifier fills this now-wider
            card's width instead of staying a small inline-flex pill hugging
            the left edge (2026-09-08, per the user). */}
        <div className="ac-criticality-toggle stretch">
          {ASSIGNMENT_FILTER_OPTIONS.map((opt) => (
            <button type="button" key={opt.key} className={value === opt.key ? "active" : ""} onClick={() => onChange(opt.key)}>
              {opt.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function renderStatusCard(
  card: StatusCardResponse,
  statusFilter: string | null,
  onSelect: (key: string) => void,
  activeFilter: string | null,
  // Draws a thin vertical rule before this card — used to demarcate
  // Unassigned from the L5-L1 group when they share one row (Deviation/
  // Market Complaint/no filter; OOS/OOT already separate them into two
  // rows instead — see the caller) (2026-09-08, per the user). A wrapper,
  // not a style on .ac-status-card itself, so it doesn't fight that card's
  // own (possibly colored) border.
  dividerBefore = false
) {
  // card.key is already the CSS class ("unassigned", "phase1", "phase2",
  // "L5".."L1") — just lowercased, to match ActionCenterPage.css's
  // .l5/.l4/.l3/.l2/.l1 rules ("unassigned"/"phase1"/"phase2" fall through
  // to the plain default .ac-status-card look, no override needed).
  const cssClass = card.key.toLowerCase();
  const icon = STATUS_ICONS[cssClass];
  const levelCaptions = activeFilter === "Market Complaint" ? LEVEL_CAPTION_MARKET_COMPLAINT : LEVEL_CAPTION_DEFAULT;
  const caption = levelCaptions[card.key];
  const isActive = statusFilter === card.key;
  // Only L5-L1 get the selected-dot — they're the only cards whose color
  // fill is otherwise off by default (2026-09-08, per the user); unassigned/
  // phase1/phase2 keep the plain box-shadow ring instead (see .ac-status-
  // card.active in the CSS).
  const isLevelCard = /^l[1-5]$/.test(cssClass);
  const card_ = (
    <div
      className={`ac-status-card ${cssClass} ${isActive ? "active" : ""}`}
      onClick={() => onSelect(card.key)}
    >
      {isActive && isLevelCard && <span className="ac-status-active-dot" />}
      <div className="ac-status-card-header">
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {icon && <img src={icon} alt="" width={18} height={18} />}
          {card.label}
        </span>
        <span className="ac-status-count">{card.count}</span>
      </div>
      {caption && <div className="ac-status-card-caption">{caption}</div>}
    </div>
  );
  if (!dividerBefore) return <div key={card.key}>{card_}</div>;
  return (
    <div key={card.key} style={{ borderLeft: "1px solid var(--color-card-border)", paddingLeft: 8 }}>
      {card_}
    </div>
  );
}

const PAGE_SIZE = 10;

// Numbered pager (Figma node 1229:38395) — always shows first/last plus a
// window around the current page, collapsing the rest into an ellipsis so
// this stays usable at real page counts (45+), unlike Figma's 2-page mock.
function pageNumbers(current: number, total: number): (number | "…")[] {
  const pages = new Set<number>([1, total, current, current - 1, current + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
  const result: (number | "…")[] = [];
  sorted.forEach((p, idx) => {
    if (idx > 0 && p - sorted[idx - 1] > 1) result.push("…");
    result.push(p);
  });
  return result;
}

export function ActionCenterPage() {
  const { roles, viewAsInvestigator } = useAuth();
  // Anyone with the SIT (Site Inspection Team) role, or Admin, sees "SIT
  // Dashboard" as the page title instead of "Action Center" (2026-08-18, per
  // the user; made role-based instead of a single hardcoded account on
  // 2026-09-03; swapped from User to Admin on 2026-09-04, per the user) —
  // the plain "User" role sees "Action Center" (when not viewing as a
  // specific investigator, which has its own title).
  const showsSitDashboardTitle = roles.includes("SIT") || roles.includes("Admin");
  const [summary, setSummary] = useState<ActionCenterSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [previewInvestigation, setPreviewInvestigation] = useState<PreviewInvestigation | null>(null);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  // Status-card click filter (2026-08-19, per the user) — same client-side
  // toggle-filter UX as the event-type pills (activeFilter above), just
  // scoped to a card's bucket instead of an event type. For OOS/OOT this
  // still also covers Unassigned/Phase 1/Phase 2 (unchanged) — Deviation/
  // Market Complaint/no-filter use it for L5-L1 only, see assignmentFilter
  // below for their separate Assigned/Unassigned axis.
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  // All/Assigned/Unassigned radio group, replacing the plain "Unassigned"
  // card for Deviation/Market Complaint/no-filter (2026-09-08, per the
  // user) — a genuinely independent filter dimension from level (statusFilter
  // above): both can be set at once (e.g. Assigned + L3), neither clears the
  // other. Not shown for OOS/OOT, whose Unassigned concept stays coupled
  // with level via statusFilter as before — reset back to "all" on any
  // event-type change so a hidden selection never silently keeps filtering
  // once OOS/OOT hides the radio group (same reset convention as
  // criticalityFilter below).
  const [assignmentFilter, setAssignmentFilter] = useState<"all" | "assigned" | "unassigned">("all");
  useEffect(() => {
    setAssignmentFilter("all");
  }, [activeFilter]);
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");
  // Card View's grouping toggle (SIT Dashboard Figma, 2026-09-04, per the
  // user) — genuine group-by, not a value filter: Card View always shows
  // every matching investigation, just organized into named sections by
  // product or by investigator instead of one flat grid. "all" (added
  // 2026-09-04, per the user) shows the plain ungrouped flat grid.
  const [groupBy, setGroupBy] = useState<"all" | "product" | "investigator">("product");
  const [page, setPage] = useState(1);
  const [siteFilter, setSiteFilter] = useState("");
  const [deptFilter, setDeptFilter] = useState("");
  const [productFilter, setProductFilter] = useState("");
  const [investigatorFilter, setInvestigatorFilter] = useState("");
  // Default view excludes cancelled investigations entirely (2026-08-13, per
  // the user) — toggled on via a button rather than mixed into the normal
  // list.
  const [showCancelled, setShowCancelled] = useState(false);
  // Page-wide filter (2026-08-14, per the user) — unlike showCancelled above,
  // this narrows stat cards/chart/pending actions AND the investigations
  // table alike, same as site/department/product/investigator/date.
  const [criticalityFilter, setCriticalityFilter] = useState("");
  // The criticality/phase toggle switches its whole option set between
  // Critical/Major & Minor and Critical/Phase 1/Phase 2 depending on the
  // event type selected above (2026-08-25, per the user) — a value from one
  // set (e.g. "phase1") is meaningless in the other, so switching event
  // types resets the toggle back to "All" rather than carrying it over.
  useEffect(() => {
    setCriticalityFilter("");
  }, [activeFilter]);
  const [searchQuery, setSearchQuery] = useState("");
  const [sortColumn, setSortColumn] = useState<SortColumn | null>(null);

  // Demo "view as" control from the account menu (2026-08-14, per the user) —
  // reuses the existing investigator filter to reproduce that investigator's
  // whole-page view (stat cards/chart/pending actions/table alike) rather
  // than adding a separate scoping mechanism. Runs whenever the header
  // selection changes, including back to null (clears the filter).
  useEffect(() => {
    setInvestigatorFilter(viewAsInvestigator ?? "");
    setPage(1);
  }, [viewAsInvestigator]);
  // Clears the Site filter back to "All Sites" on leaving investigator view
  // — deliberately keyed only on viewAsInvestigator (not summary), so this
  // never fires while the admin is browsing normally and picks their own
  // site filter (which also triggers a summary refetch).
  useEffect(() => {
    if (!viewAsInvestigator) setSiteFilter("");
  }, [viewAsInvestigator]);
  // Once that investigator's data comes back, the Site filter reflects their
  // real site instead of "All Sites" — the Investigator filter pill itself
  // is hidden entirely while in this view (rendered further down), since
  // picking a different investigator here would fight the header's own
  // control (2026-08-21, per the user).
  useEffect(() => {
    if (!viewAsInvestigator || !summary) return;
    const site = summary.investigations.find((inv) => inv.investigator === viewAsInvestigator)?.site;
    if (site) setSiteFilter(site);
  }, [viewAsInvestigator, summary]);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setDbError(null);
    getActionCenterSummary({
      site: siteFilter || undefined,
      department: deptFilter || undefined,
      product: productFilter || undefined,
      investigator: investigatorFilter || undefined,
      status: showCancelled ? "cancelled" : "open",
      criticality:
        criticalityFilter === "critical" || criticalityFilter === "non_critical" ? criticalityFilter : undefined,
      oosOotPhase: criticalityFilter === "phase1" || criticalityFilter === "phase2" ? criticalityFilter : undefined,
    })
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch((err) => {
        if (!cancelled) setDbError(err instanceof ApiError ? String(err.detail) : "Could not reach the database.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [retryKey, siteFilter, deptFilter, productFilter, investigatorFilter, showCancelled, criticalityFilter]);

  // Only show the full-page skeleton on the very first load. Once we have a
  // summary, a filter-driven refetch just dims the existing content in place
  // (see the opacity below) instead of unmounting everything — avoids the
  // jarring full-page reload feel on every filter change.
  if (loading && !summary) {
    return (
      <div className="ac-page-bg">
        <div className="ac-page">
          <div className="card">
            <p className="card-title">Loading Action Center…</p>
          </div>
        </div>
      </div>
    );
  }

  if (dbError || !summary) {
    return <DbErrorModal message={dbError ?? "No data returned."} onRetry={() => setRetryKey((k) => k + 1)} />;
  }

  // Selecting an L5-L1 card narrows the event-type pill counts/percentages
  // the same way selecting an event type already narrows the status cards
  // via status_cards_by_event_type (2026-08-25, per the user) — computed
  // client-side from the same already-fetched summary.investigations list
  // the table itself filters, rather than a new backend field, since every
  // investigation's event_type/bucket is already right there. Unassigned/
  // Phase 1/Phase 2 are excluded from this (2026-09-07, per the user) — they
  // still filter the table and the other status cards, just not the
  // event-type pills above.
  const _NO_EVENT_TYPE_BACKFILTER = new Set(["unassigned", "phase1", "phase2"]);
  const eventTypePillStatusFilter = statusFilter && !_NO_EVENT_TYPE_BACKFILTER.has(statusFilter) ? statusFilter : null;
  const statusFilteredInvestigations = summary.investigations.filter(
    (inv) => !eventTypePillStatusFilter || matchesStatusCard(inv, eventTypePillStatusFilter)
  );
  const eventTypeCounts = summary.event_type_counts.map((s) => {
    const count = statusFilteredInvestigations.filter((inv) => inv.event_type === s.label).length;
    return {
      ...s,
      count,
      // Rounded to 1 decimal place (2026-09-08, per the user) — was a whole
      // number before.
      percent: statusFilteredInvestigations.length > 0 ? Math.round((count / statusFilteredInvestigations.length) * 1000) / 10 : 0,
    };
  });

  const visibleInvestigations = summary.investigations
    .filter((inv) => !activeFilter || inv.event_type === activeFilter)
    .filter((inv) => !statusFilter || matchesStatusCard(inv, statusFilter))
    .filter((inv) => {
      if (assignmentFilter === "all") return true;
      const isUnassigned = inv.bucket === "unassigned";
      return assignmentFilter === "unassigned" ? isUnassigned : !isUnassigned;
    })
    .filter((inv) => {
      if (!searchQuery.trim()) return true;
      const q = searchQuery.trim().toLowerCase();
      return (
        inv.id.toLowerCase().includes(q) ||
        inv.title.toLowerCase().includes(q) ||
        (inv.investigator ?? "").toLowerCase().includes(q) ||
        (inv.product ?? "").toLowerCase().includes(q) ||
        inv.rci_ids.some((rciId) => rciId.toLowerCase().includes(q))
      );
    });
  const sortedInvestigations = sortColumn
    ? [...visibleInvestigations].sort((a, b) =>
        compareForSort(getSortValue(a, sortColumn), getSortValue(b, sortColumn), sortDirection)
      )
    : [...visibleInvestigations].sort((a, b) => {
        const bucketDiff = (DEFAULT_SORT_BUCKET_PRIORITY[a.bucket] ?? 4) - (DEFAULT_SORT_BUCKET_PRIORITY[b.bucket] ?? 4);
        if (bucketDiff !== 0) return bucketDiff;
        return compareForSort(parseDisplayDateMs(a.due_date), parseDisplayDateMs(b.due_date), "asc");
      });
  // All 4 status cards always show, even when scoped to one investigator (via
  // the filter dropdown or the header's "view as" demo control) who happens to
  // have zero investigations in a given bucket — a zero count is still shown
  // rather than the card disappearing (2026-08-21, per the user; previously
  // "Unassigned" was hidden entirely for investigator views).
  // Clicking one status card (Unassigned/Phase 1/Phase 2/L5-L1) narrows
  // every OTHER card's own displayed count too (2026-09-07, per the user) —
  // same "selecting one filter recomputes the rest" pattern as
  // statusFilteredInvestigations above, since these are independent
  // dimensions now (an investigation can be both Unassigned and L1), not a
  // partition — e.g. clicking Unassigned should show how many of THOSE are
  // L1 vs L2, not just repeat the unscoped L1/L2 totals. When no status
  // filter is active this recomputes to the same number the backend
  // already sent, just via the same matchesStatusCard logic the table uses.
  const eventTypeScopedInvestigations = summary.investigations.filter((inv) => !activeFilter || inv.event_type === activeFilter);
  const statusCards = (activeFilter ? summary.status_cards_by_event_type[activeFilter] ?? summary.status_cards : summary.status_cards).map(
    (card) => ({
      ...card,
      // Recomputed against assignmentFilter too (2026-09-08, per the user)
      // — selecting Assigned/Unassigned via the Status pill now narrows
      // L5-L1's own displayed counts the same way statusFilter already did,
      // instead of always showing the full per-level total regardless of
      // which assignment state is selected. A no-op when assignmentFilter
      // is "all" (its default/reset value), so this doesn't change anything
      // for OOS/OOT, which never shows that pill.
      count: eventTypeScopedInvestigations.filter(
        (inv) =>
          matchesStatusCard(inv, card.key) &&
          (!statusFilter || matchesStatusCard(inv, statusFilter)) &&
          (assignmentFilter === "all" || (inv.bucket === "unassigned") === (assignmentFilter === "unassigned"))
      ).length,
    })
  );
  const chartData = summary.chart.map((c) => ({ label: c.label, onTrack: c.on_track, atRisk: c.at_risk, delayed: c.delayed }));

  const totalPages = Math.max(1, Math.ceil(sortedInvestigations.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedInvestigations = sortedInvestigations.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  // Card View's grouped sections — built from every sorted+filtered
  // investigation, not just the current page, since a group split across
  // pages would show as incomplete/duplicated sections. Grouping and
  // List View's pagination are mutually exclusive views of the same data,
  // matching the Figma mock (no pager shown alongside grouped cards). "all"
  // is a single unnamed group — Card View renders it as one flat grid, no
  // section header (see the "all" branch in the render below).
  const groupedInvestigations: { name: string; items: InvestigationRowResponse[] }[] = (() => {
    if (groupBy === "all") return [{ name: "", items: sortedInvestigations }];
    const groups = new Map<string, InvestigationRowResponse[]>();
    for (const inv of sortedInvestigations) {
      const raw = groupBy === "investigator" ? inv.investigator : inv.product;
      const name = raw && raw.trim() ? raw : "Unassigned";
      if (!groups.has(name)) groups.set(name, []);
      groups.get(name)!.push(inv);
    }
    return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([name, items]) => ({ name, items }));
  })();

  function handleSort(column: SortColumn) {
    if (sortColumn === column) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortColumn(column);
      setSortDirection("asc");
    }
    setPage(1);
  }

  function setFilter(label: string) {
    setActiveFilter((prev) => (prev === label ? null : label));
    setPage(1);
  }

  function setStatusCardFilter(key: string) {
    setStatusFilter((prev) => (prev === key ? null : key));
    setPage(1);
  }

  function toPreview(inv: InvestigationRowResponse): PreviewInvestigation {
    return {
      id: inv.id,
      title: inv.title,
      eventType: inv.event_type,
      investigator: inv.investigator ?? "",
      step: inv.stage,
      totalSteps: inv.total_stages,
      dueDate: inv.due_date ?? "—",
      lastUpdated: inv.updated_at ?? "—",
    };
  }

  function renderInvestigationCard(inv: InvestigationRowResponse) {
    const percent = Math.round((inv.stage / inv.total_stages) * 100);
    const statusInfo = BUCKET_TO_STATUS[inv.bucket] ?? BUCKET_TO_STATUS.unassigned;
    const initials = (inv.investigator ?? "")
      .split(" ")
      .filter(Boolean)
      .map((part) => part[0])
      .join("")
      .toUpperCase();
    return (
      <div className="ac-card" key={inv.id} onClick={() => setPreviewInvestigation(toPreview(inv))} style={{ cursor: "pointer" }}>
        <div className="ac-inv-card-header">
          <span className="ac-pending-card-id">{inv.id}</span>
          <span className={`status-pill ${statusInfo.status}`}>{statusInfo.label}</span>
        </div>
        <p className="ac-pending-card-title">{inv.title}</p>
        <div className="ac-inv-tag-row">
          <span className="ac-inv-tag">{inv.event_type}</span>
          <span className="ac-inv-tag">Start date: {inv.start_date ?? "—"}</span>
          <span className="ac-inv-tag">Due date: {inv.due_date ?? "—"}</span>
        </div>
        {inv.investigator && (
          <div className="ac-inv-investigator-row">
            <span className="ac-inv-avatar">{initials}</span>
            <div>
              <div className="ac-inv-investigator-name">{inv.investigator}</div>
              <div className="ac-inv-investigator-role">INVESTIGATOR</div>
            </div>
          </div>
        )}
        {inv.is_cancelled ? (
          <span className="status-pill cancelled">Cancelled</span>
        ) : (
          <>
            <div className="ac-inv-progress-label">
              <span>PROGRESS</span>
              <span>{inv.stage}/{inv.total_stages}</span>
            </div>
            <div className="ac-progress-track">
              <div className="ac-progress-fill" style={{ width: `${percent}%` }} />
            </div>
            <p className="ac-inv-progress-caption">{percent}% complete</p>
          </>
        )}
      </div>
    );
  }

  return (
    <>
    <div className="ac-page-bg">
    <div className="ac-page" style={{ opacity: loading ? 0.6 : 1, transition: "opacity 150ms ease" }}>
      <h1 className="ac-title">
        {viewAsInvestigator
          ? `Action Center - Investigator View (${viewAsInvestigator})`
          : showsSitDashboardTitle
            ? "SIT Dashboard"
            : "Action Center"}
      </h1>

      {/* 5 equal-width KPI cards — Open Investigations plus one per event
          type, each with its own monthly bar chart + MoM trend (SIT
          Dashboard Figma, 2026-09-04, per the user) — replaces the old
          single "Open Investigations" card + flat stat-pill row. */}
      <div className="ac-kpi-row">
        {/* Open Investigations resets back to the all-types default view
            (2026-09-07, per the user) — the other 4 cards scope down to one
            event type, this one clears that scope. */}
        <div
          className={`ac-kpi-card neutral ${activeFilter === null ? "active" : ""}`}
          onClick={() => {
            setActiveFilter(null);
            setPage(1);
          }}
        >
          <div className="ac-kpi-card-header">OPEN INVESTIGATIONS</div>
          <div className="ac-kpi-card-count">{summary.total_investigations}</div>
          <div className="ac-kpi-card-subtitle">4 event types · 6-step workflow</div>
          {renderKpiChart(summary.opened_trend, "Opened / month", "neutral", true)}
        </div>
        {eventTypeCounts.map((s) => (
          <div
            className={`ac-kpi-card ${eventTypeAccentClass(s.label)} ${activeFilter === s.label ? "active" : ""}`}
            key={s.label}
            onClick={() => setFilter(s.label)}
          >
            {activeFilter === s.label && <span className="ac-kpi-active-dot" />}
            <div className="ac-kpi-card-header">{s.label.toUpperCase()}</div>
            <div className="ac-kpi-card-count">{s.count}</div>
            <div className="ac-kpi-card-subtitle">{s.percent}% of open</div>
            {renderKpiChart(s.closed_trend, "Closed / month")}
          </div>
        ))}
      </div>

      {/* Unassigned only splits into its own row above L5-L1 when Phase
          1/Phase 2 are also present (i.e. scoped to OOS/OOT) — every other
          selection keeps all 6 cards in one line (2026-09-07, per the
          user). */}
      {(() => {
        const topRowKeys = new Set(["unassigned", "phase1", "phase2"]);
        const topRow = statusCards.filter((c) => topRowKeys.has(c.key));
        const levelRow = statusCards.filter((c) => !topRowKeys.has(c.key));
        if (topRow.length <= 1) {
          // Deviation/Market Complaint/no filter: "Unassigned" is a radio
          // group (All/Assigned/Unassigned) instead of a plain card here —
          // OOS/OOT (topRow.length > 1) keeps the old plain card, untouched,
          // in the branch below (2026-09-08, per the user).
          const levelOnlyCards = statusCards.filter((c) => c.key !== "unassigned");
          return (
            <div
              className="ac-status-row"
              // Status gets 1.5x a level card's width (2026-09-08, per the
              // user — dialed back from 2fr, which read as too big) so its
              // segmented All/Assigned/Unassigned control has a bit more
              // room to stretch out than a single level card's 1fr.
              style={{ gridTemplateColumns: `1.5fr repeat(${levelOnlyCards.length}, 1fr)` }}
            >
              {renderAssignmentFilterCard(assignmentFilter, setAssignmentFilter)}
              {levelOnlyCards.map((card, idx) => renderStatusCard(card, statusFilter, setStatusCardFilter, activeFilter, idx === 0))}
            </div>
          );
        }
        return (
          <>
            <div className="ac-status-row" style={{ gridTemplateColumns: `repeat(${topRow.length}, 1fr)` }}>
              {topRow.map((card) => renderStatusCard(card, statusFilter, setStatusCardFilter, activeFilter))}
            </div>
            <div className="ac-status-row" style={{ gridTemplateColumns: `repeat(${levelRow.length}, 1fr)` }}>
              {levelRow.map((card) => renderStatusCard(card, statusFilter, setStatusCardFilter, activeFilter))}
            </div>
          </>
        );
      })()}

      {false && (
      <div>
        <h2 className="ac-section-title" style={{ marginBottom: 12 }}>Pending Actions</h2>
        <div className="ac-pending-grid">
            {summary!.pending_actions.map((action) => {
              // Pending actions carry a summary shape (no investigator/stage)
              // — look up the matching full row from summary.investigations
              // (same source list backend-side) to build the same
              // PreviewInvestigation the table/grid rows use.
              const fullInvestigation = summary!.investigations.find((inv) => inv.id === action.id);
              // Fixed two-row layout: row 1 = OOS, row 2 = Deviation (see
              // action_center.py) — explicit gridRow so the split stays
              // correct even when one side has fewer than 3 cards, rather
              // than letting grid auto-placement slide the next group up.
              const gridRow = action.event_type === "OOS" ? 1 : 2;
              return (
                <div
                  className="ac-card"
                  key={action.id}
                  onClick={() => fullInvestigation && setPreviewInvestigation(toPreview(fullInvestigation))}
                  style={{ cursor: fullInvestigation ? "pointer" : undefined, gridRow }}
                >
                  <div className="ac-pending-card-header">
                    <span className="ac-pending-card-id">{action.id}</span>
                    {action.is_overdue && <span className="ac-badge critical">Overdue</span>}
                  </div>
                  <p className="ac-pending-card-title">{action.title}</p>
                  <div className="ac-pending-action-row">
                    {!action.is_unassigned && fullInvestigation?.investigator && (
                      <span className="ac-pending-card-investigator">{fullInvestigation.investigator}</span>
                    )}
                    {action.is_unassigned && <span className="ac-badge gray">Unassigned</span>}
                    {action.criticality === "Critical" && <span className="ac-badge critical">Critical</span>}
                    <span className="ac-badge due">Due date: {action.due_date ?? "—"}</span>
                  </div>
                  <p className="ac-pending-action-label">ACTION</p>
                  <p className="ac-pending-action-desc">{action.action}</p>
                </div>
              );
            })}
            {summary!.pending_actions.length === 0 && (
              <p style={{ color: "var(--color-text-muted)" }}>No pending actions right now.</p>
            )}
          </div>
        </div>
      )}

      {false && (
      <div className="ac-card">
        <h2 className="ac-section-title" style={{ marginBottom: 16 }}>Status Of Open Investigations</h2>
        <StatusChart data={chartData} />
      </div>
      )}

      {/* Filters section — criticality toggle, dropdown filters, and search
          all live here now, separate from the Investigation Details table
          below (SIT Dashboard Figma, 2026-09-04, per the user) — previously
          all of this, plus the table itself, shared one card. */}
      <div className="ac-card">
        {/* Search + every filter now share one line, search shortened and
            pinned to the left with the whole filter group shifted to its
            right (2026-09-09, per the user) — previously the search bar
            was its own full-width row below this one. */}
        <div className="ac-details-header" style={{ flexWrap: "nowrap" }}>
          {/* flex: 1 (2026-09-09, per the user) — expands to fill the space
              up to the filter group instead of stopping at a short fixed
              width, so the row reads as one unbroken line with no dead gap
              between the search bar and the filters. */}
          <div className="ac-search-row" style={{ marginBottom: 0, flex: 1 }}>
            <div className="ac-search-input-wrap">
              <img src={iconSearch} alt="" width={16} height={16} />
              <input
                className="ac-search-input"
                placeholder="Search title, record ID, RCI ID, investigator, product..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPage(1);
                }}
              />
            </div>
            <button type="button" className="ac-search-btn">Search</button>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", justifyContent: "flex-end" }}>
            <div className="ac-criticality-toggle">
              <button
                type="button"
                className={criticalityFilter === "" ? "active" : ""}
                onClick={() => {
                  setCriticalityFilter("");
                  setPage(1);
                }}
              >
                All
              </button>
              <button
                type="button"
                className={criticalityFilter === "critical" ? "active" : ""}
                onClick={() => {
                  setCriticalityFilter("critical");
                  setPage(1);
                }}
              >
                Critical
              </button>
              {activeFilter === "OOS" || activeFilter === "OOT" ? (
                <>
                  <button
                    type="button"
                    className={criticalityFilter === "phase2" ? "active" : ""}
                    onClick={() => {
                      setCriticalityFilter("phase2");
                      setPage(1);
                    }}
                  >
                    Phase 2
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className={criticalityFilter === "non_critical" ? "active" : ""}
                  onClick={() => {
                    setCriticalityFilter("non_critical");
                    setPage(1);
                  }}
                >
                  Major & Minor
                </button>
              )}
            </div>
            <CriticalityGuidelines eventType={activeFilter} />
            <div className="ac-filters">
              <FilterSelect
                className="ac-filter-pill"
                value={siteFilter}
                onChange={(v) => {
                  setSiteFilter(v);
                  setPage(1);
                }}
                defaultLabel="All Sites"
                options={summary.filter_options.sites}
                formatOption={formatSiteLabel}
              />
              <FilterSelect
                className="ac-filter-pill"
                value={deptFilter}
                onChange={(v) => {
                  setDeptFilter(v);
                  setPage(1);
                }}
                defaultLabel="Dept"
                options={summary.filter_options.departments}
              />
              <FilterSelect
                className="ac-filter-pill"
                value={productFilter}
                onChange={(v) => {
                  setProductFilter(v);
                  setPage(1);
                }}
                defaultLabel="Product"
                options={summary.filter_options.products}
              />
              {!viewAsInvestigator && (
                <FilterSelect
                  className="ac-filter-pill"
                  value={investigatorFilter}
                  onChange={(v) => {
                    setInvestigatorFilter(v);
                    setPage(1);
                  }}
                  defaultLabel="All Investigators"
                  options={summary.filter_options.investigators}
                  formatOption={formatInvestigatorLabel}
                />
              )}
              {/* Button removed (2026-08-25, per the user: never show cancelled
                  deviations) — showCancelled/setShowCancelled and the
                  status: "cancelled" query branch are kept as-is below, just
                  unreachable with no way to toggle this on. */}
              {false && (
                <button
                  type="button"
                  className={`ac-filter-pill${showCancelled ? " active" : ""}`}
                  onClick={() => {
                    setShowCancelled((v) => !v);
                    setPage(1);
                  }}
                >
                  {showCancelled ? "Showing Cancelled" : "Show Cancelled"}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="ac-card">
        <div className="ac-details-header">
          <div className="ac-details-title-group">
            <h2>Investigation Details</h2>
            <p>{summary.total_investigations} investigations total</p>
          </div>
          <div className="ac-view-toggle">
            <button
              type="button"
              aria-label="Grid view"
              className={viewMode === "grid" ? "active" : ""}
              onClick={() => setViewMode("grid")}
            >
              <img src={iconViewGrid} alt="" width={20} height={20} />
            </button>
            <button
              type="button"
              aria-label="List view"
              className={viewMode === "list" ? "active" : ""}
              onClick={() => setViewMode("list")}
            >
              <img src={iconViewList} alt="" width={20} height={20} />
            </button>
          </div>
        </div>

        {/* Card View's group-by toggle (SIT Dashboard Figma, 2026-09-04, per
            the user) — no List View equivalent, matches the Figma mock. */}
        {viewMode === "grid" && (
          <div className="ac-details-header" style={{ marginTop: -8 }}>
            <div className="ac-criticality-toggle">
              <button type="button" className={groupBy === "all" ? "active" : ""} onClick={() => setGroupBy("all")}>
                All
              </button>
              <button type="button" className={groupBy === "product" ? "active" : ""} onClick={() => setGroupBy("product")}>
                By Product
              </button>
              <button type="button" className={groupBy === "investigator" ? "active" : ""} onClick={() => setGroupBy("investigator")}>
                By Investigator
              </button>
            </div>
            <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
              {groupBy === "all"
                ? `${sortedInvestigations.length} investigations`
                : `${groupedInvestigations.length} ${groupBy === "investigator" ? "investigators" : "products"}`}
            </span>
          </div>
        )}

        {viewMode === "list" ? (
          <table className="ac-table">
            <thead>
              <tr>
                <th>Investigation</th>
                {SORTABLE_COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}
                  >
                    {col.label}
                    {col.key === "due_date" && (
                      <span style={{ marginLeft: 4, display: "inline-flex" }} onClick={(e) => e.stopPropagation()}>
                        <InfoTooltip label="How the due date is calculated">
                          <p style={{ margin: 0, fontSize: "var(--font-size-base)" }}>
                            Due date is 30 days from the start date for Deviation, OOS, and OOT events, and 55 days from the start date for Market Complaints.
                          </p>
                        </InfoTooltip>
                      </span>
                    )}
                    {sortColumn === col.key && (
                      <span style={{ marginLeft: 4, fontSize: "var(--font-size-xs)" }}>{sortDirection === "asc" ? "▲" : "▼"}</span>
                    )}
                  </th>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {pagedInvestigations.map((inv) => {
                const percent = Math.round((inv.stage / inv.total_stages) * 100);
                const statusInfo = BUCKET_TO_STATUS[inv.bucket] ?? BUCKET_TO_STATUS.unassigned;
                return (
                  <tr
                    key={inv.id}
                    className={`ac-inv-row ${eventTypeAccentClass(inv.event_type)}`}
                    onClick={() => setPreviewInvestigation(toPreview(inv))}
                    style={{ cursor: "pointer" }}
                  >
                    <td>
                      <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                        <span className={`ac-badge ${eventTypeAccentClass(inv.event_type)}`}>{inv.event_type}</span>
                        {/* Major/Minor no longer get a badge (2026-09-08, per the user) —
                            only Critical is called out on the row. */}
                        {inv.criticality === "Critical" && <span className="ac-badge critical">Critical</span>}
                      </div>
                      <div className="ac-inv-id">{inv.id}{inv.rci_ids.length > 0 ? ` / ${inv.rci_ids.join(", ")}` : ""}</div>
                      <div className="ac-inv-title">{inv.title}</div>
                    </td>
                    <td>{inv.product ?? "—"}</td>
                    <td>{inv.investigator ?? "Unassigned"}</td>
                    <td className="ac-progress-cell">
                      {inv.is_cancelled ? (
                        <span className="status-pill cancelled">Cancelled</span>
                      ) : (
                        <>
                          <div className="ac-progress-top">
                            <span>{inv.stage}/{inv.total_stages} steps</span>
                            <span>{percent}%</span>
                          </div>
                          <div className="ac-progress-track">
                            <div className="ac-progress-fill" style={{ width: `${percent}%` }} />
                          </div>
                        </>
                      )}
                    </td>
                    <td>{inv.start_date ?? "—"}</td>
                    <td>{inv.due_date ?? "—"}</td>
                    <td className="ac-status-cell">
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span>{statusInfo.label}</span>
                        {inv.escalation_level && ESCALATION_TONE[inv.escalation_level] && (
                          <span className={`escalation-bubble ${ESCALATION_TONE[inv.escalation_level]}`}>
                            {inv.escalation_level}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="ac-row-arrow"
                        aria-label={`Preview ${inv.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setPreviewInvestigation(toPreview(inv));
                        }}
                      >
                        <img src={iconRowArrow} alt="" width={14} height={14} style={{ transform: "rotate(180deg)" }} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="ac-grouped-sections">
            {groupedInvestigations.map((group, idx) => (
              <div key={group.name || idx} className="ac-group-section">
                {groupBy !== "all" && (
                  <div className="ac-group-header">
                    {groupBy === "investigator" && (
                      <span className="ac-inv-avatar">
                        {group.name
                          .split(" ")
                          .filter(Boolean)
                          .map((part) => part[0])
                          .join("")
                          .toUpperCase()}
                      </span>
                    )}
                    <span className="ac-group-name">{group.name}</span>
                    <span className="ac-group-count">{group.items.length}</span>
                  </div>
                )}
                <div className="ac-pending-grid">{group.items.map(renderInvestigationCard)}</div>
              </div>
            ))}
          </div>
        )}

        {/* Card View's groups always show every matching investigation, not
            a page at a time (see groupedInvestigations above) — pagination
            only applies to the flat List View table. */}
        {viewMode === "list" && (
          <div className="ac-pagination">
            <button
              type="button"
              className="ac-page-btn"
              aria-label="Previous page"
              disabled={currentPage <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ‹
            </button>
            {pageNumbers(currentPage, totalPages).map((p, idx) =>
              p === "…" ? (
                <span key={`ellipsis-${idx}`} style={{ fontSize: "var(--font-size-base)", color: "var(--color-text-muted)", padding: "0 4px" }}>
                  …
                </span>
              ) : (
                <button
                  key={p}
                  type="button"
                  className={`ac-page-btn ${p === currentPage ? "active" : ""}`}
                  aria-label={`Page ${p}`}
                  aria-current={p === currentPage ? "page" : undefined}
                  onClick={() => setPage(p)}
                >
                  {p}
                </button>
              )
            )}
            <button
              type="button"
              className="ac-page-btn"
              aria-label="Next page"
              disabled={currentPage >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              ›
            </button>
          </div>
        )}
      </div>
    </div>
    </div>
    <InvestigationPreviewPanel investigation={previewInvestigation} onClose={() => setPreviewInvestigation(null)} />
    </>
  );
}
