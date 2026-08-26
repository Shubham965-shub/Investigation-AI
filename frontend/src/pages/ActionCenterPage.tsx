import { useEffect, useState } from "react";
import { StatusChart } from "../components/StatusChart";
import { InvestigationPreviewPanel, type PreviewInvestigation } from "../components/InvestigationPreviewPanel";
import { DbErrorModal } from "../components/DbErrorModal";
import { FilterSelect } from "../components/FilterSelect";
import { InfoTooltip } from "../components/InfoTooltip";
import { CriticalityGuidelines } from "../components/CriticalityGuidelines";
import { formatSiteLabel } from "../constants/siteLabels";
import { ApiError } from "../api/client";
import { getActionCenterSummary, type ActionCenterSummaryResponse, type InvestigationRowResponse, type StatusCardResponse } from "../api/dashboard";
import { useAuth } from "../auth/AuthContext";
import iconUnassigned from "../assets/icons/status-unassigned.svg";
import iconOnTrack from "../assets/icons/status-on-track.svg";
import iconDelay from "../assets/icons/status-delay.svg";
import iconOverdue from "../assets/icons/status-overdue.svg";
import iconSearch from "../assets/icons/search.svg";
import iconViewGrid from "../assets/icons/view-grid.png";
import iconViewList from "../assets/icons/view-list.png";
import iconRowArrow from "../assets/icons/row-arrow.svg";
import "./ActionCenterPage.css";

const STATUS_ICONS: Record<string, string> = {
  unassigned: iconUnassigned,
  "on-track": iconOnTrack,
  delay: iconDelay,
  overdue: iconOverdue,
};

// Maps each status card's backend key to the css class + icon it should
// reuse. See src/routers/action_center.py for how these buckets are computed.
const CARD_KEY_TO_CSS_CLASS: Record<string, string> = {
  unassigned: "unassigned",
  unassigned_phase1: "unassigned",
  "on-track": "on-track",
  delay: "delay",
  overdue: "overdue",
};

// Status cards use hyphenated keys ("on-track") while each investigation
// row's own bucket field uses underscores ("on_track") — see
// action_center.py's _bucket_for/_OPEN_STATUS_TO_BUCKET vs its status-card
// building. Needed to filter the table by clicking a card (2026-08-19, per
// the user, same click-to-filter UX as the event-type pills below).
const CARD_KEY_TO_BUCKET: Record<string, string> = {
  unassigned: "unassigned",
  unassigned_phase1: "unassigned",
  "on-track": "on_track",
  delay: "delay",
  overdue: "overdue",
};

// The Unassigned bucket itself splits into two status-card pills
// (2026-08-25, per the user): "Phase 1 OOS/OOT" for Phase 1 OOS/OOT
// investigations only, and "Unassigned" for everything else (Deviations,
// Market Complaints, and Phase 2 — or not-yet-phased — OOS/OOT). Bucket
// alone can't tell those apart, so this checks oos_oot_phase too instead of
// a plain CARD_KEY_TO_BUCKET lookup.
function matchesStatusCard(inv: InvestigationRowResponse, cardKey: string): boolean {
  if (cardKey === "unassigned_phase1") return inv.bucket === "unassigned" && inv.oos_oot_phase === "Phase 1";
  if (cardKey === "unassigned") return inv.bucket === "unassigned" && inv.oos_oot_phase !== "Phase 1";
  return inv.bucket === CARD_KEY_TO_BUCKET[cardKey];
}

// Real backend bucket -> the table/grid status-pill styling + label.
const BUCKET_TO_STATUS: Record<string, { status: string; label: string }> = {
  unassigned: { status: "unassigned", label: "Unassigned" },
  delay: { status: "due-soon", label: "At Risk of Delay" },
  on_track: { status: "in-progress", label: "In Progress" },
  overdue: { status: "overdue", label: "Overdue" },
};

// dim_event.escalation_level ("L1".."L5", or "Not Applicable"/null for most
// rows) -> the same tone as the status bucket it corresponds to (per the
// user): L1/L2 = on-track, L3/L4 = at-risk-of-delay, L5 = overdue.
const ESCALATION_TONE: Record<string, "success" | "warning" | "danger"> = {
  L1: "success",
  L2: "success",
  L3: "warning",
  L4: "warning",
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
type SortColumn = "event_type" | "investigator" | "progress" | "start_date" | "due_date" | "status";

const SORTABLE_COLUMNS: { key: SortColumn; label: string }[] = [
  { key: "event_type", label: "Event Type" },
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
    case "event_type":
      return inv.event_type;
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

// Supervisor variant of the Action Center (see project memory: Action Center
// has CXO/Supervisor/Investigator variants — CXO is on hold, Investigator
// filters this same data down to the current user). Real data as of
// 2026-07-24, sourced from GET /action-center/summary — see project memory:
// action_center_roles for the business-rule placeholders this endpoint
// encodes (status buckets, pending actions, progress chart).

function renderStatusCard(card: StatusCardResponse, active: boolean, onClick: () => void) {
  const cssClass = CARD_KEY_TO_CSS_CLASS[card.key] ?? "unassigned";
  return (
    <div className={`ac-status-card ${cssClass} ${active ? "active" : ""}`} key={card.key} onClick={onClick}>
      <div className="ac-status-card-header">
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <img src={STATUS_ICONS[cssClass]} alt="" width={18} height={18} />
          {card.label}
        </span>
        <span className="ac-status-count">{card.count}</span>
      </div>
      {card.rows.map(([label, count]) => (
        <div className="ac-status-subrow" key={label}>
          <span>{label}</span>
          <span>{count}</span>
        </div>
      ))}
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
  const { username, viewAsInvestigator } = useAuth();
  // Ajay Pathania's account is SIT (Site Inspection Team), not a generic
  // admin (2026-08-18, per the user) — everyone else still defaults to
  // "Admin View" when not viewing as a specific investigator.
  const isSitAccount = username?.toLowerCase() === "pathania.ajay@strides.com";
  const [summary, setSummary] = useState<ActionCenterSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [previewInvestigation, setPreviewInvestigation] = useState<PreviewInvestigation | null>(null);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  // Status-card click filter (2026-08-19, per the user) — same client-side
  // toggle-filter UX as the event-type pills (activeFilter above), just
  // scoped to a card's bucket instead of an event type.
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");
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

  // Selecting a status pill (Unassigned/On Track/Delay/Overdue) narrows the
  // event-type pill counts/percentages the same way selecting an event type
  // already narrows the status cards via status_cards_by_event_type
  // (2026-08-25, per the user) — computed client-side from the same
  // already-fetched summary.investigations list the table itself filters,
  // rather than a new backend field, since every investigation's
  // event_type/bucket is already right there.
  const statusFilteredInvestigations = summary.investigations.filter(
    (inv) => !statusFilter || matchesStatusCard(inv, statusFilter)
  );
  const eventTypeCounts = summary.event_type_counts.map((s) => {
    const count = statusFilteredInvestigations.filter((inv) => inv.event_type === s.label).length;
    return { ...s, count, percent: statusFilteredInvestigations.length > 0 ? Math.round((count / statusFilteredInvestigations.length) * 100) : 0 };
  });

  const visibleInvestigations = summary.investigations
    .filter((inv) => !activeFilter || inv.event_type === activeFilter)
    .filter((inv) => !statusFilter || matchesStatusCard(inv, statusFilter))
    .filter((inv) => {
      if (!searchQuery.trim()) return true;
      const q = searchQuery.trim().toLowerCase();
      return (
        inv.id.toLowerCase().includes(q) ||
        inv.title.toLowerCase().includes(q) ||
        (inv.investigator ?? "").toLowerCase().includes(q) ||
        (inv.product ?? "").toLowerCase().includes(q)
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
  const statusCards = activeFilter ? summary.status_cards_by_event_type[activeFilter] ?? summary.status_cards : summary.status_cards;
  const chartData = summary.chart.map((c) => ({ label: c.label, onTrack: c.on_track, atRisk: c.at_risk, delayed: c.delayed }));

  const totalPages = Math.max(1, Math.ceil(sortedInvestigations.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedInvestigations = sortedInvestigations.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

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

  return (
    <>
    <div className="ac-page-bg">
    <div className="ac-page" style={{ opacity: loading ? 0.6 : 1, transition: "opacity 150ms ease" }}>
      <h1 className="ac-title">
        Action Center{viewAsInvestigator ? ` - Investigator View (${viewAsInvestigator})` : isSitAccount ? " - SIT View" : " - Admin View"}
      </h1>

      <section className="ac-card">
        <div className="ac-total-header">
          <h2>Open Investigations</h2>
          <span className="ac-total-count">{summary.total_investigations}</span>
        </div>
        <div className="ac-stat-pills">
          {eventTypeCounts.map((s) => (
            <div
              className={`ac-stat-pill ${activeFilter === s.label ? "active" : ""}`}
              key={s.label}
              onClick={() => setFilter(s.label)}
            >
              <span>{s.label}</span>
              <span>
                <span className="ac-stat-count">{s.count}</span>
                <span className="ac-stat-percent">({s.percent}%)</span>
              </span>
            </div>
          ))}
        </div>
      </section>

      <div className="ac-status-row" style={{ gridTemplateColumns: `repeat(${statusCards.length}, 1fr)` }}>
        {statusCards.map((card) => renderStatusCard(card, statusFilter === card.key, () => setStatusCardFilter(card.key)))}
      </div>

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

      <div className="ac-card">
        <div className="ac-details-header">
          <div className="ac-details-title-group">
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <h2>Investigation Details</h2>
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
            </div>
            <p>{summary.total_investigations} investigations total</p>
          </div>
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

        <div className="ac-search-row">
          <div className="ac-search-input-wrap">
            <img src={iconSearch} alt="" width={16} height={16} />
            <input
              className="ac-search-input"
              placeholder="Search here..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <button type="button" className="ac-search-btn">Search</button>
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
                  <tr key={inv.id} onClick={() => setPreviewInvestigation(toPreview(inv))} style={{ cursor: "pointer" }}>
                    <td>
                      <div className="ac-inv-id">{inv.id}</div>
                      <div className="ac-inv-title">{inv.title}</div>
                    </td>
                    <td>{inv.event_type}</td>
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
          <div className="ac-pending-grid">
            {pagedInvestigations.map((inv) => {
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
            })}
          </div>
        )}

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
      </div>
    </div>
    </div>
    <InvestigationPreviewPanel investigation={previewInvestigation} onClose={() => setPreviewInvestigation(null)} />
    </>
  );
}
