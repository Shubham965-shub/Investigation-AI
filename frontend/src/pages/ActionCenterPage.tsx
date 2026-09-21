import { Fragment, useEffect, useRef, useState } from "react";
import { StatusChart } from "../components/StatusChart";
import { InvestigationPreviewPanel, type PreviewInvestigation } from "../components/InvestigationPreviewPanel";
import { DbErrorModal } from "../components/DbErrorModal";
import { FilterSelect } from "../components/FilterSelect";
import { InfoTooltip } from "../components/InfoTooltip";
import { CriticalityGuidelines } from "../components/CriticalityGuidelines";
import { formatSiteLabel } from "../constants/siteLabels";
import { ApiError } from "../api/client";
import { getActionCenterSummary, updateInvestigationRemark, type ActionCenterSummaryResponse, type InvestigationRowResponse, type MonthlyTrend, type StatusCardResponse } from "../api/dashboard";
import { useAuth } from "../auth/AuthContext";
import iconUnassigned from "../assets/icons/status-unassigned.svg";
import iconSearch from "../assets/icons/search.svg";
import iconViewGrid from "../assets/icons/view-grid.png";
import iconViewList from "../assets/icons/view-list.png";
import iconRowArrow from "../assets/icons/row-arrow.svg";
import { formatLastUpdated } from "../utils/formatTimestamp";
import "./ActionCenterPage.css";

// Only "Unassigned" gets an icon; renderStatusCard skips the <img> when a card's key has no entry here.
const STATUS_ICONS: Record<string, string> = {
  unassigned: iconUnassigned,
};

// Unassigned and L5-L1 are independent dimensions, not a partition — an investigation can be both Unassigned and L1, so this uses `bucket` rather than deriving "unassigned" from a missing escalation_level.
function matchesStatusCard(inv: InvestigationRowResponse, cardKey: string): boolean {
  // Phase 1/Phase 2 are standalone cards, independent of assignment status — only present when scoped to OOS/OOT.
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

// escalation_level ("L1".."L5") -> one distinct tone per level, matching the status cards above.
const ESCALATION_TONE: Record<string, "success" | "info" | "warning" | "pink" | "danger"> = {
  L1: "success",
  L2: "info",
  L3: "warning",
  L4: "pink",
  L5: "danger",
};

// Default order sorts by bucket (Trackwise's own status), not raw due_date — due_date alone can't reliably reproduce it. Ties break by earliest due date.
const DEFAULT_SORT_BUCKET_PRIORITY: Record<string, number> = {
  overdue: 0,
  delay: 1,
  on_track: 2,
  unassigned: 3,
};


// Must match the backend's _UNASSIGNED_INVESTIGATOR_FILTER sentinel exactly.
const UNASSIGNED_INVESTIGATOR_FILTER = "__unassigned__";

function formatInvestigatorLabel(investigator: string): string {
  return investigator === UNASSIGNED_INVESTIGATOR_FILTER ? "Unassigned" : investigator;
}

// Every column except "Investigation" itself is sortable.
type SortColumn = "product" | "investigator" | "progress" | "start_date" | "due_date" | "status";

const SORTABLE_COLUMNS: { key: SortColumn; label: string }[] = [
  { key: "product", label: "Product" },
  { key: "investigator", label: "Investigator" },
  { key: "progress", label: "Progress" },
  { key: "start_date", label: "Start Date" },
  { key: "due_date", label: "Due Date" },
  { key: "status", label: "Status" },
];

// Dates are pre-formatted strings ("29 Jul 2026"), not ISO — parse to a timestamp so sort is chronological, not alphabetical by month name.
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
      return inv.total_stages ? inv.investigator_stage / inv.total_stages : 0;
    case "start_date":
      return parseDisplayDateMs(inv.start_date);
    case "due_date":
      return parseDisplayDateMs(inv.due_date);
    case "status":
      return inv.is_cancelled ? "Cancelled" : (BUCKET_TO_STATUS[inv.bucket] ?? BUCKET_TO_STATUS.unassigned).label;
  }
}

// Nulls always sort to the end regardless of direction — flipping them on "desc" would put blanks first.
function compareForSort(a: string | number | null, b: string | number | null, direction: "asc" | "desc"): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  const cmp = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));
  return direction === "asc" ? cmp : -cmp;
}

// Grey (neutral) when trend is 0/undefined — previous month's count was 0, so a % change isn't meaningful.
function trendTone(trendPercent: number | null): "neutral" | "warm" | "cool" {
  if (!trendPercent) return "neutral";
  return trendPercent < 0 ? "warm" : "cool";
}

// Static per event type, independent of the MoM trend coloring above.
function eventTypeAccentClass(label: string): "event-deviation" | "event-oos" | "event-oot" | "event-mc" {
  if (label === "OOS") return "event-oos";
  if (label === "OOT") return "event-oot";
  if (label === "Market Complaint") return "event-mc";
  return "event-deviation";
}

// Only Major/Minor show here, no "Non Critical" tag — null means unclassified or no Major/Minor concept (OOS/OOT), not "non-critical". Critical itself is a separate badge driven by criticality.
function classificationFlag(inv: InvestigationRowResponse): { label: string; className: string } | null {
  if (inv.event_classification === "Major") return { label: "Major", className: "classification-major" };
  if (inv.event_classification === "Minor") return { label: "Minor", className: "classification-minor" };
  return null;
}

// Bar heights are computed as a JS pixel value, not CSS %, since % height doesn't resolve reliably through this flex chain.
const KPI_CHART_HEIGHT_PX = 40;

// Rounds max up to a "nice" axis ceiling (1-2-5-10 step sequence) so bars stay proportional to a real 0 baseline, with headroom above the tallest bar.
function niceAxisMax(max: number, targetSteps = 4): number {
  if (max <= 0) return 1;
  const rawStep = max / targetSteps;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
  return Math.ceil(max / step) * step;
}

// forceTone="neutral" opts a card out of trend-based coloring (used for Open Investigations). invertTrendColor flips good/bad direction for "Opened / month", where more is bad unlike "Closed / month".
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

// Sourced from GET /action-center/summary — see project memory (action_center_roles) for the business-rule placeholders this endpoint encodes.

// Per-level day-range captions, copied verbatim from the Figma mock — frontend-only display text, not derived from a real threshold in this codebase.
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

// Replaces the plain "Unassigned" card for Deviation/Market Complaint/no-filter — filters independently of the L5-L1 level filter.
function renderAssignmentFilterCard(
  value: "all" | "assigned" | "unassigned",
  onChange: (v: "all" | "assigned" | "unassigned") => void,
  assignedCount: number,
  unassignedCount: number
) {
  return (
    <div className="ac-status-card unassigned" key="assignment-filter">
      <div className="ac-status-card-header">
        <span>Status</span>
      </div>
      <div style={{ padding: "0 20px 20px" }}>
        {/* Reuses .ac-criticality-toggle styling; "stretch" fills the wider card's width instead of a small inline pill. */}
        <div className="ac-criticality-toggle stretch">
          {ASSIGNMENT_FILTER_OPTIONS.map((opt) => (
            <button type="button" key={opt.key} className={value === opt.key ? "active" : ""} onClick={() => onChange(opt.key)}>
              {opt.label}
            </button>
          ))}
        </div>
        {/* Counts respect the event-type pill + status card filters, not the Assigned/Unassigned toggle itself — both always show. */}
        <p style={{ margin: "10px 0 0", fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)", textAlign: "center" }}>
          Assigned: {assignedCount} · Unassigned: {unassignedCount}
        </p>
      </div>
    </div>
  );
}

function renderStatusCard(
  card: StatusCardResponse,
  statusFilter: string | null,
  onSelect: (key: string) => void,
  activeFilter: string | null,
  // Draws a divider before this card, to separate Unassigned from L5-L1 when they share one row.
  dividerBefore = false
) {
  // Lowercased to match ActionCenterPage.css's .l5/.l4/.l3/.l2/.l1 rules.
  const cssClass = card.key.toLowerCase();
  const icon = STATUS_ICONS[cssClass];
  const levelCaptions = activeFilter === "Market Complaint" ? LEVEL_CAPTION_MARKET_COMPLAINT : LEVEL_CAPTION_DEFAULT;
  const caption = levelCaptions[card.key];
  const isActive = statusFilter === card.key;
  // Only L5-L1 get the selected-dot; unassigned/phase1/phase2 use the plain box-shadow ring instead.
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

// Shows first/last plus a window around the current page, collapsing the rest into an ellipsis for large page counts.
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
  // SIT or Admin roles see "SIT Dashboard" as the title; plain "User" sees "Action Center".
  const showsSitDashboardTitle = roles.includes("SIT") || roles.includes("Admin");
  // Backend already scopes `summary` to this investigator's own rows; Open Investigations KPI and "All Investigators" filter are hidden here since they'd be redundant.
  const isInvestigatorRole = roles.includes("Investigator");
  // Remark column: viewable by SIT or Admin, editable by SIT only — the backend enforces both independently too.
  const canViewRemarks = roles.includes("SIT") || roles.includes("Admin");
  const canEditRemarks = roles.includes("SIT");
  const [remarkDrafts, setRemarkDrafts] = useState<Record<string, string>>({});
  const [remarkSaving, setRemarkSaving] = useState<Record<string, boolean>>({});
  const [remarkErrors, setRemarkErrors] = useState<Record<string, string>>({});
  // Keyed by deviation_id (inv.id) — unique per row now that rows aren't exploded one-per-rci_id.
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [summary, setSummary] = useState<ActionCenterSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [previewInvestigation, setPreviewInvestigation] = useState<PreviewInvestigation | null>(null);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  // Same toggle-filter UX as activeFilter, scoped to a card's bucket; assignmentFilter below covers Assigned/Unassigned separately.
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  // Reset on event-type change — otherwise a stale selection from the previous event type silently keeps filtering.
  useEffect(() => {
    setStatusFilter(null);
  }, [activeFilter]);
  // Independent filter dimension from statusFilter — both can be set at once (e.g. Assigned + L3). Not shown for OOS/OOT.
  const [assignmentFilter, setAssignmentFilter] = useState<"all" | "assigned" | "unassigned">("all");
  useEffect(() => {
    setAssignmentFilter("all");
  }, [activeFilter]);
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");
  // Double-clicking the "Progress" column header toggles a second column showing the original
  // TrackWise-status-based progress bar alongside the default Investigator-generated one.
  const [showTwStatusColumn, setShowTwStatusColumn] = useState(false);
  const progressClickTimer = useRef<number | null>(null);
  // Genuine group-by, not a filter — every matching investigation still shows, just organized into sections. "all" = flat grid.
  const [groupBy, setGroupBy] = useState<"all" | "product" | "investigator">("product");
  const [page, setPage] = useState(1);
  const [siteFilter, setSiteFilter] = useState("");
  const [deptFilter, setDeptFilter] = useState("");
  const [productFilter, setProductFilter] = useState("");
  const [investigatorFilter, setInvestigatorFilter] = useState("");
  // Cancelled investigations are excluded by default.
  const [showCancelled, setShowCancelled] = useState(false);
  // Narrows stat cards/chart/pending actions and the table alike, unlike showCancelled.
  const [criticalityFilter, setCriticalityFilter] = useState("");
  // Toggle's option set changes with event type (Critical/Major&Minor vs Critical/Phase1&2) — reset on switch since a value like "phase1" is meaningless in the other set.
  useEffect(() => {
    setCriticalityFilter("");
  }, [activeFilter]);
  const [searchQuery, setSearchQuery] = useState("");
  const [sortColumn, setSortColumn] = useState<SortColumn | null>(null);

  // "View as" reuses the investigator filter to reproduce that investigator's whole-page view.
  useEffect(() => {
    setInvestigatorFilter(viewAsInvestigator ?? "");
    setPage(1);
  }, [viewAsInvestigator]);
  // Keyed only on viewAsInvestigator (not summary) so this doesn't fire during normal admin site-filter browsing.
  useEffect(() => {
    if (!viewAsInvestigator) setSiteFilter("");
  }, [viewAsInvestigator]);
  // Site filter is set to the investigator's real site once their data arrives.
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

  // Full-page skeleton only on first load — later refetches just dim existing content instead of unmounting.
  if (loading && !summary) {
    return (
      <div className="ac-page-bg">
        <div className="ac-page">
          <div className="card">
            <p className="card-title">Loading Dashboard…</p>
          </div>
        </div>
      </div>
    );
  }

  if (dbError || !summary) {
    return <DbErrorModal message={dbError ?? "No data returned."} onRetry={() => setRetryKey((k) => k + 1)} />;
  }

  // Selecting a level card narrows event-type pill counts too, computed client-side. Unassigned/Phase1/Phase2 are excluded from this back-filter.
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
      percent: statusFilteredInvestigations.length > 0 ? Math.round((count / statusFilteredInvestigations.length) * 1000) / 10 : 0,
    };
  });

  // Rows are one per real investigation — a multi-RCI investigation is a single row that expands into an accordion (see expandedIds) rather than being exploded one-per-rci_id.
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
  // Status cards always show even at a zero count, rather than disappearing.
  // Clicking one status card narrows every other card's own count too, since these are independent dimensions (not a partition).
  const eventTypeScopedInvestigations = summary.investigations.filter((inv) => !activeFilter || inv.event_type === activeFilter);
  // L1-L5 are mutually exclusive — cross-narrowing one level's count by another selected level would always be 0, so skip narrowing when both are levels.
  const isLevelKey = (key: string) => /^L[1-5]$/.test(key);
  const statusCards = (activeFilter ? summary.status_cards_by_event_type[activeFilter] ?? summary.status_cards : summary.status_cards).map(
    (card) => {
      const sameLevelDimension = isLevelKey(card.key) && isLevelKey(statusFilter ?? "");
      return {
        ...card,
        // Also narrowed by assignmentFilter — a no-op when it's "all" (OOS/OOT never shows that pill).
        count: eventTypeScopedInvestigations.filter(
          (inv) =>
            matchesStatusCard(inv, card.key) &&
            (!statusFilter || sameLevelDimension || matchesStatusCard(inv, statusFilter)) &&
            (assignmentFilter === "all" || (inv.bucket === "unassigned") === (assignmentFilter === "unassigned"))
        ).length,
      };
    }
  );
  const chartData = summary.chart.map((c) => ({ label: c.label, onTrack: c.on_track, atRisk: c.at_risk, delayed: c.delayed }));

  const totalPages = Math.max(1, Math.ceil(sortedInvestigations.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedInvestigations = sortedInvestigations.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  // Built from every filtered investigation, not just the current page — a group split across pages would look incomplete.
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

  // Native double-click fires click, click, then dblclick — without this, double-clicking the
  // Progress header to toggle the TW Status column would also sort-by-progress twice as an
  // unwanted side effect. Debounces the single click just for this column so a second click
  // arriving in time cancels it and lets handleProgressDoubleClick take over instead.
  function handleProgressHeaderClick() {
    if (progressClickTimer.current !== null) return;
    progressClickTimer.current = window.setTimeout(() => {
      progressClickTimer.current = null;
      handleSort("progress");
    }, 250);
  }
  function handleProgressHeaderDoubleClick() {
    if (progressClickTimer.current !== null) {
      window.clearTimeout(progressClickTimer.current);
      progressClickTimer.current = null;
    }
    setShowTwStatusColumn((prev) => !prev);
  }

  function setFilter(label: string) {
    setActiveFilter((prev) => (prev === label ? null : label));
    setPage(1);
  }

  function setStatusCardFilter(key: string) {
    setStatusFilter((prev) => (prev === key ? null : key));
    setPage(1);
  }

  // Autosaves on blur. rowKey mirrors the row's composite key (`${inv.id}-${rciId}`) so each accordion sub-row's draft stays independent.
  async function saveRemark(inv: InvestigationRowResponse, rciId: string, rowKey: string, value: string) {
    const previouslySaved = inv.remarks[rciId] ?? "";
    if (value === previouslySaved) return;
    setRemarkSaving((prev) => ({ ...prev, [rowKey]: true }));
    setRemarkErrors((prev) => ({ ...prev, [rowKey]: "" }));
    try {
      await updateInvestigationRemark(inv.id, rciId, value);
    } catch (err) {
      setRemarkErrors((prev) => ({ ...prev, [rowKey]: err instanceof ApiError ? String(err.detail) : "Failed to save remark" }));
    } finally {
      setRemarkSaving((prev) => ({ ...prev, [rowKey]: false }));
    }
  }

  function toggleExpanded(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
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
      <div className="ac-card" key={`${inv.id}-${inv.rci_ids[0] ?? ""}`} onClick={() => setPreviewInvestigation(toPreview(inv))} style={{ cursor: "pointer" }}>
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
        {/* Hidden when already grouped by investigator — that group header already names them. */}
        {inv.investigator && groupBy !== "investigator" && (
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
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <h1 className="ac-title">
          {viewAsInvestigator
            ? `Action Center - Investigator View (${viewAsInvestigator})`
            : showsSitDashboardTitle
              ? "SIT Dashboard"
              : "Action Center"}
        </h1>
        {/* fact_qms_event.pg_updated_at_timestamp — a flat bulk-load stamp, same value on every row. */}
        {formatLastUpdated(summary.last_updated_at) && (
          <span style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
            {formatLastUpdated(summary.last_updated_at)}
          </span>
        )}
      </div>

      {/* Open Investigations card is dropped for the Investigator role — it's a cross-investigator total, meaningless when already scoped to one person. */}
      <div className="ac-kpi-row" style={isInvestigatorRole ? { gridTemplateColumns: "repeat(4, 1fr)" } : undefined}>
        {/* Clears the event-type scope back to the all-types default view. */}
        {!isInvestigatorRole && (
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
            {!viewAsInvestigator && renderKpiChart(summary.opened_trend, "Opened / month", "neutral", true)}
          </div>
        )}
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
            {!isInvestigatorRole && !viewAsInvestigator && renderKpiChart(s.closed_trend, "Closed / month")}
          </div>
        ))}
      </div>

      {/* Unassigned splits into its own row only when Phase 1/Phase 2 are present (OOS/OOT scope). */}
      {(() => {
        // Sourced from summary.investigations (one row per real investigation), scoped to the active event-type pill + status card.
        const scopedForAssignmentCounts = eventTypeScopedInvestigations
          .filter((inv) => !statusFilter || matchesStatusCard(inv, statusFilter));
        const unassignedCount = scopedForAssignmentCounts.filter((inv) => inv.bucket === "unassigned").length;
        const assignedCount = scopedForAssignmentCounts.length - unassignedCount;

        const topRowKeys = new Set(["unassigned", "phase1", "phase2"]);
        const topRow = statusCards.filter((c) => topRowKeys.has(c.key));
        const levelRow = statusCards.filter((c) => !topRowKeys.has(c.key));
        if (topRow.length <= 1) {
          // Deviation/Market Complaint/no filter: "Unassigned" is a radio
          // group (All/Assigned/Unassigned) instead of a plain card here.
          const levelOnlyCards = statusCards.filter((c) => c.key !== "unassigned");
          return (
            <div
              className="ac-status-row"
              // Status gets 1.5x a level card's width so its segmented control has room to stretch.
              style={{ gridTemplateColumns: `1.5fr repeat(${levelOnlyCards.length}, 1fr)` }}
            >
              {renderAssignmentFilterCard(assignmentFilter, setAssignmentFilter, assignedCount, unassignedCount)}
              {levelOnlyCards.map((card, idx) => renderStatusCard(card, statusFilter, setStatusCardFilter, activeFilter, idx === 0))}
            </div>
          );
        }
        // OOS/OOT: Phase1/Phase2 keep their own row; Status pill shares the L5-L1 row below, same 1.5fr layout as above.
        const topRowWithoutUnassigned = topRow.filter((c) => c.key !== "unassigned");
        return (
          <>
            <div
              className="ac-status-row"
              style={{ gridTemplateColumns: `repeat(${topRowWithoutUnassigned.length}, 1fr)` }}
            >
              {topRowWithoutUnassigned.map((card) => renderStatusCard(card, statusFilter, setStatusCardFilter, activeFilter))}
            </div>
            <div
              className="ac-status-row"
              style={{ gridTemplateColumns: `1.5fr repeat(${levelRow.length}, 1fr)` }}
            >
              {renderAssignmentFilterCard(assignmentFilter, setAssignmentFilter, assignedCount, unassignedCount)}
              {levelRow.map((card, idx) => renderStatusCard(card, statusFilter, setStatusCardFilter, activeFilter, idx === 0))}
            </div>
          </>
        );
      })()}

      {false && (
      <div>
        <h2 className="ac-section-title" style={{ marginBottom: 12 }}>Pending Actions</h2>
        <div className="ac-pending-grid">
            {summary!.pending_actions.map((action) => {
              // Look up the full row from summary.investigations to build a PreviewInvestigation.
              const fullInvestigation = summary!.investigations.find((inv) => inv.id === action.id);
              // Explicit gridRow (row 1 = OOS, row 2 = Deviation) keeps the split correct even with fewer than 3 cards per side.
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

      <div className="ac-card">
        <div className="ac-details-header" style={{ flexWrap: "nowrap" }}>
          {/* flex: 1 fills space up to the filter group so there's no dead gap before it. */}
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
              {!viewAsInvestigator && !isInvestigatorRole && (
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
              {/* Cancelled deviations are never shown; showCancelled/setShowCancelled stay wired but unreachable. */}
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
              aria-label="List view"
              className={viewMode === "list" ? "active" : ""}
              onClick={() => setViewMode("list")}
            >
              <img src={iconViewList} alt="" width={14} height={14} />
              List View
            </button>
            <button
              type="button"
              aria-label="Card view"
              className={viewMode === "grid" ? "active" : ""}
              onClick={() => setViewMode("grid")}
            >
              <img src={iconViewGrid} alt="" width={14} height={14} />
              Card View
            </button>
          </div>
        </div>

        {/* Group-by toggle — Card View only, no List View equivalent. */}
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
                  <Fragment key={col.key}>
                    <th
                      onClick={col.key === "progress" ? handleProgressHeaderClick : () => handleSort(col.key)}
                      onDoubleClick={col.key === "progress" ? handleProgressHeaderDoubleClick : undefined}
                      title={col.key === "progress" ? "Double-click to toggle the TrackWise-status column" : undefined}
                      style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}
                    >
                      {col.label}
                      {col.key === "due_date" && (
                        <span style={{ marginLeft: 4, display: "inline-flex" }} onClick={(e) => e.stopPropagation()}>
                          <InfoTooltip label="How the due date is calculated">
                            <p style={{ margin: 0, fontSize: "var(--font-size-base)" }}>
                              Due date is 30 days from initiation of event in TW for Deviation, OOS, and OOT events, and 55 days from initiation of event in TW for Market Complaints.
                            </p>
                          </InfoTooltip>
                        </span>
                      )}
      {sortColumn === col.key && (
                        <span style={{ marginLeft: 4, fontSize: "var(--font-size-xs)" }}>{sortDirection === "asc" ? "▲" : "▼"}</span>
                      )}
                    </th>
                    {col.key === "progress" && showTwStatusColumn && (
                      <th style={{ whiteSpace: "nowrap" }}>TW Status</th>
                    )}
                  </Fragment>
                ))}
                {canViewRemarks && <th>Remark</th>}
                <th />
              </tr>
            </thead>
            <tbody>
              {pagedInvestigations.flatMap((inv) => {
                const percent = Math.round((inv.investigator_stage / inv.total_stages) * 100);
                const twPercent = Math.round((inv.stage / inv.total_stages) * 100);
                const statusInfo = BUCKET_TO_STATUS[inv.bucket] ?? BUCKET_TO_STATUS.unassigned;
                const hasMultipleRci = inv.rci_ids.length > 1;
                const isExpanded = expandedIds.has(inv.id);
                const primaryRciId = inv.rci_ids[0] ?? "";
                const rowKey = `${inv.id}-${primaryRciId}`;
                const remarkValue = remarkDrafts[rowKey] ?? inv.remarks[primaryRciId] ?? "";

                const summaryRow = (
                  <tr
                    key={inv.id}
                    className={`ac-inv-row ${eventTypeAccentClass(inv.event_type)}`}
                    onClick={() => (hasMultipleRci ? toggleExpanded(inv.id) : setPreviewInvestigation(toPreview(inv)))}
                    style={{ cursor: "pointer" }}
                  >
                    <td>
                      <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                        <span className={`ac-badge ${eventTypeAccentClass(inv.event_type)}`}>{inv.event_type}</span>
                        {(() => {
                          const flag = classificationFlag(inv);
                          return flag && <span className={`ac-badge ${flag.className}`}>{flag.label}</span>;
                        })()}
                        {inv.criticality === "Critical" && <span className="ac-badge critical">Critical</span>}
                      </div>
                      <div className="ac-inv-id" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        {inv.id}
                        {inv.rci_ids.length > 0 ? ` / ${inv.rci_ids.join(", ")}` : ""}
                        {hasMultipleRci && (
                          <span aria-hidden style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
                            {isExpanded ? "▾" : "▸"}
                          </span>
                        )}
                      </div>
                      <div className="ac-inv-title">{inv.title}</div>
                    </td>
                    <td>{inv.product ?? "—"}</td>
                    <td>{hasMultipleRci ? "—" : inv.investigator ?? "Unassigned"}</td>
                    <td className="ac-progress-cell">
                      {hasMultipleRci ? (
                        "—"
                      ) : inv.is_cancelled ? (
                        <span className="status-pill cancelled">Cancelled</span>
                      ) : (
                        <>
                          <div className="ac-progress-top">
                            <span>{inv.investigator_stage}/{inv.total_stages} steps</span>
                            <span>{percent}%</span>
                          </div>
                          <div className="ac-progress-track">
                            <div className="ac-progress-fill" style={{ width: `${percent}%` }} />
                          </div>
                        </>
                      )}
                    </td>
                    {showTwStatusColumn && (
                      <td className="ac-progress-cell">
                        {hasMultipleRci ? (
                          "—"
                        ) : inv.is_cancelled ? (
                          <span className="status-pill cancelled">Cancelled</span>
                        ) : (
                          <>
                            <div className="ac-progress-top">
                              <span>{inv.stage}/{inv.total_stages} steps</span>
                              <span>{twPercent}%</span>
                            </div>
                            <div className="ac-progress-track">
                              <div className="ac-progress-fill" style={{ width: `${twPercent}%` }} />
                            </div>
                          </>
                        )}
                      </td>
                    )}
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
                    {canViewRemarks && (
                      <td onClick={(e) => e.stopPropagation()}>
                        {hasMultipleRci ? (
                          <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>See below</span>
                        ) : (
                          <>
                            <textarea
                              className="ac-remark-input"
                              rows={2}
                              placeholder={canEditRemarks ? "Add a remark…" : "No remark yet"}
                              value={remarkValue}
                              readOnly={!canEditRemarks}
                              title={!canEditRemarks ? "Only the SIT role can edit remarks" : undefined}
                              onChange={canEditRemarks ? (e) => setRemarkDrafts((prev) => ({ ...prev, [rowKey]: e.target.value })) : undefined}
                              onBlur={canEditRemarks ? (e) => saveRemark(inv, primaryRciId, rowKey, e.target.value) : undefined}
                            />
                            {canEditRemarks && remarkSaving[rowKey] && (
                              <p style={{ margin: "2px 0 0", fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>Saving…</p>
                            )}
                            {canEditRemarks && remarkErrors[rowKey] && (
                              <p style={{ margin: "2px 0 0", fontSize: "var(--font-size-xs)", color: "var(--color-danger-text)" }}>{remarkErrors[rowKey]}</p>
                            )}
                          </>
                        )}
                      </td>
                    )}
                    <td>
                      <button
                        type="button"
                        className="ac-row-arrow"
                        aria-label={hasMultipleRci ? `Toggle ${inv.id}` : `Preview ${inv.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (hasMultipleRci) toggleExpanded(inv.id);
                          else setPreviewInvestigation(toPreview(inv));
                        }}
                      >
                        <img
                          src={iconRowArrow}
                          alt=""
                          width={14}
                          height={14}
                          style={{ transform: hasMultipleRci ? (isExpanded ? "rotate(90deg)" : "rotate(0deg)") : "rotate(180deg)" }}
                        />
                      </button>
                    </td>
                  </tr>
                );

                if (!hasMultipleRci || !isExpanded) return [summaryRow];

                // One sub-row per rci_id; title/product/dates/status stay blank since they're already shown on the summary row above.
                const subRows = inv.rci_ids.map((rciId) => {
                  const subRowKey = `${inv.id}-${rciId}`;
                  const subRemarkValue = remarkDrafts[subRowKey] ?? inv.remarks[rciId] ?? "";
                  const subInvestigator = rciId in inv.investigator_by_rci ? inv.investigator_by_rci[rciId] : inv.investigator;
                  return (
                    <tr
                      key={subRowKey}
                      className={`ac-inv-row ac-inv-subrow ${eventTypeAccentClass(inv.event_type)}`}
                      onClick={() =>
                        setPreviewInvestigation(toPreview({ ...inv, rci_ids: [rciId], investigator: subInvestigator }))
                      }
                      style={{ cursor: "pointer" }}
                    >
                      <td style={{ paddingLeft: 32 }}>
                        <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>↳ RCI {rciId}</span>
                      </td>
                      <td>—</td>
                      <td>{subInvestigator ?? "Unassigned"}</td>
                      <td className="ac-progress-cell">
                        {inv.is_cancelled ? (
                          <span className="status-pill cancelled">Cancelled</span>
                        ) : (
                          <>
                            <div className="ac-progress-top">
                              <span>{inv.investigator_stage}/{inv.total_stages} steps</span>
                              <span>{percent}%</span>
                            </div>
                            <div className="ac-progress-track">
                              <div className="ac-progress-fill" style={{ width: `${percent}%` }} />
                            </div>
                          </>
                        )}
                      </td>
                      {showTwStatusColumn && (
                        <td className="ac-progress-cell">
                          {inv.is_cancelled ? (
                            <span className="status-pill cancelled">Cancelled</span>
                          ) : (
                            <>
                              <div className="ac-progress-top">
                                <span>{inv.stage}/{inv.total_stages} steps</span>
                                <span>{twPercent}%</span>
                              </div>
                              <div className="ac-progress-track">
                                <div className="ac-progress-fill" style={{ width: `${twPercent}%` }} />
                              </div>
                            </>
                          )}
                        </td>
                      )}
                      <td>—</td>
                      <td>—</td>
                      <td>—</td>
                      {canViewRemarks && (
                        <td onClick={(e) => e.stopPropagation()}>
                          <textarea
                            className="ac-remark-input"
                            rows={2}
                            placeholder={canEditRemarks ? "Add a remark…" : "No remark yet"}
                            value={subRemarkValue}
                            readOnly={!canEditRemarks}
                            title={!canEditRemarks ? "Only the SIT role can edit remarks" : undefined}
                            onChange={canEditRemarks ? (e) => setRemarkDrafts((prev) => ({ ...prev, [subRowKey]: e.target.value })) : undefined}
                            onBlur={canEditRemarks ? (e) => saveRemark(inv, rciId, subRowKey, e.target.value) : undefined}
                          />
                          {canEditRemarks && remarkSaving[subRowKey] && (
                            <p style={{ margin: "2px 0 0", fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>Saving…</p>
                          )}
                          {canEditRemarks && remarkErrors[subRowKey] && (
                            <p style={{ margin: "2px 0 0", fontSize: "var(--font-size-xs)", color: "var(--color-danger-text)" }}>{remarkErrors[subRowKey]}</p>
                          )}
                        </td>
                      )}
                      <td />
                    </tr>
                  );
                });

                return [summaryRow, ...subRows];
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

        {/* Pagination only applies to List View — Card View always shows every matching investigation. */}
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
