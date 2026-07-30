import { useEffect, useState } from "react";
import { StatusChart } from "../components/StatusChart";
import { InvestigationPreviewPanel, type PreviewInvestigation } from "../components/InvestigationPreviewPanel";
import { DbErrorModal } from "../components/DbErrorModal";
import { ApiError } from "../api/client";
import { getActionCenterSummary, type ActionCenterSummaryResponse, type StatusCardResponse } from "../api/dashboard";
import iconUnassigned from "../assets/icons/status-unassigned.svg";
import iconOnTrack from "../assets/icons/status-on-track.svg";
import iconDelay from "../assets/icons/status-delay.svg";
import iconOverdue from "../assets/icons/status-overdue.svg";
import iconSearch from "../assets/icons/search.svg";
import iconViewGrid from "../assets/icons/view-grid.png";
import iconViewList from "../assets/icons/view-list.png";
import iconChevron from "../assets/icons/filter-chevron.svg";
import iconRowArrow from "../assets/icons/row-arrow.svg";
import "./ActionCenterPage.css";

const STATUS_ICONS: Record<string, string> = {
  unassigned: iconUnassigned,
  "on-track": iconOnTrack,
  delay: iconDelay,
  overdue: iconOverdue,
};

// Backend status_cards/severity_cards use finer-grained keys (l1-l5 for the
// filtered/drill-down view) than the 4 CSS/icon variants that actually
// exist — map each card key to the css class + icon it should reuse. See
// src/routers/action_center.py for how these buckets are computed.
const CARD_KEY_TO_CSS_CLASS: Record<string, string> = {
  unassigned: "unassigned",
  "on-track": "on-track",
  delay: "delay",
  overdue: "overdue",
  l1: "delay",
  l2: "on-track",
  l3: "overdue",
  l4: "overdue",
  l5: "overdue",
};

// Real backend bucket -> the table/grid status-pill styling + label.
const BUCKET_TO_STATUS: Record<string, { status: string; label: string }> = {
  unassigned: { status: "unassigned", label: "Unassigned" },
  delay: { status: "due-soon", label: "Due Soon" },
  on_track: { status: "in-progress", label: "In Progress" },
  overdue: { status: "overdue", label: "Overdue" },
};

// Supervisor variant of the Action Center (see project memory: Action Center
// has CXO/Supervisor/Investigator variants — CXO is on hold, Investigator
// filters this same data down to the current user). Real data as of
// 2026-07-24, sourced from GET /action-center/summary — see project memory:
// action_center_roles for the business-rule placeholders this endpoint
// encodes (status buckets, pending actions, progress chart).

function renderStatusCard(card: StatusCardResponse) {
  const cssClass = CARD_KEY_TO_CSS_CLASS[card.key] ?? "unassigned";
  return (
    <div className={`ac-status-card ${cssClass}`} key={card.key}>
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

// Real filter dropdown backed by the STAR schema dimensions
// (dim_location/dim_department/dim_product/dim_investigator, via
// GET /action-center/summary's filter_options — see
// src/routers/action_center.py). Styled to match the original decorative
// ac-filter-pill look, just backed by a real <select>.
function FilterSelect({
  value,
  onChange,
  defaultLabel,
  options,
  formatOption,
}: {
  value: string;
  onChange: (value: string) => void;
  defaultLabel: string;
  options: string[];
  formatOption?: (value: string) => string;
}) {
  return (
    <div style={{ position: "relative", display: "inline-flex" }}>
      <select
        className="ac-filter-pill"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ appearance: "none", paddingRight: 28, cursor: "pointer", maxWidth: 200 }}
      >
        <option value="">{defaultLabel}</option>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {formatOption ? formatOption(opt) : opt}
          </option>
        ))}
      </select>
      <img
        src={iconChevron}
        alt=""
        width={12}
        height={12}
        style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}
      />
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
  const [summary, setSummary] = useState<ActionCenterSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [previewInvestigation, setPreviewInvestigation] = useState<PreviewInvestigation | null>(null);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");
  const [page, setPage] = useState(1);
  const [siteFilter, setSiteFilter] = useState("");
  const [deptFilter, setDeptFilter] = useState("");
  const [productFilter, setProductFilter] = useState("");
  const [investigatorFilter, setInvestigatorFilter] = useState("");
  // Preset day-count ("7"/"30"/"180") rather than a raw date-range picker —
  // matches the simple dropdown pattern the rest of this page uses. Computed
  // into an actual "start_date_from" date at fetch time.
  const [startPreset, setStartPreset] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setDbError(null);
    const startDateFrom = startPreset
      ? new Date(Date.now() - Number(startPreset) * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
      : undefined;
    getActionCenterSummary({
      site: siteFilter || undefined,
      department: deptFilter || undefined,
      product: productFilter || undefined,
      investigator: investigatorFilter || undefined,
      startDateFrom,
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
  }, [retryKey, siteFilter, deptFilter, productFilter, investigatorFilter, startPreset]);

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

  const visibleInvestigations = summary.investigations
    .filter((inv) => !activeFilter || inv.event_type === activeFilter)
    .filter((inv) => {
      if (!searchQuery.trim()) return true;
      const q = searchQuery.trim().toLowerCase();
      return inv.id.toLowerCase().includes(q) || inv.title.toLowerCase().includes(q);
    });
  const statusCards = activeFilter ? summary.severity_cards : summary.status_cards;
  const chartData = summary.chart.map((c) => ({ label: c.label, onTrack: c.on_track, atRisk: c.at_risk, delayed: c.delayed }));

  const totalPages = Math.max(1, Math.ceil(visibleInvestigations.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedInvestigations = visibleInvestigations.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  function setFilter(label: string) {
    setActiveFilter((prev) => (prev === label ? null : label));
    setPage(1);
  }

  function toPreview(inv: (typeof summary.investigations)[number]): PreviewInvestigation {
    return {
      id: inv.id,
      title: inv.title,
      eventType: inv.event_type,
      investigator: inv.investigator ?? "",
      step: inv.stage,
      totalSteps: inv.total_stages,
      dueDate: inv.due_date ?? "—",
    };
  }

  return (
    <>
    <div className="ac-page-bg">
    <div className="ac-page" style={{ opacity: loading ? 0.6 : 1, transition: "opacity 150ms ease" }}>
      <h1 className="ac-title">Action Center</h1>

      <section className="ac-card">
        <div className="ac-total-header">
          <h2>Total Investigations</h2>
          <span className="ac-total-count">{summary.total_investigations}</span>
        </div>
        <div className="ac-stat-pills">
          {summary.event_type_counts.map((s) => (
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

      <div className={`ac-status-row ${activeFilter ? "severity" : ""}`}>
        {statusCards.map(renderStatusCard)}
      </div>

      {!activeFilter && (
        <div>
          <h2 className="ac-section-title" style={{ marginBottom: 12 }}>Pending Actions</h2>
          <div className="ac-pending-grid">
            {summary.pending_actions.map((action) => {
              // Pending actions carry only a summary shape (no event_type/
              // investigator/stage) — look up the matching full row from
              // summary.investigations (same source list backend-side) to
              // build the same PreviewInvestigation the table/grid rows use.
              const fullInvestigation = summary.investigations.find((inv) => inv.id === action.id);
              return (
                <div
                  className="ac-card"
                  key={action.id}
                  onClick={() => fullInvestigation && setPreviewInvestigation(toPreview(fullInvestigation))}
                  style={{ cursor: fullInvestigation ? "pointer" : undefined }}
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
            {summary.pending_actions.length === 0 && (
              <p style={{ color: "var(--color-text-muted)" }}>No pending actions right now.</p>
            )}
          </div>
        </div>
      )}

      {!activeFilter && (
        <div className="ac-card">
          <h2 className="ac-section-title" style={{ marginBottom: 16 }}>Status Of Open Investigations</h2>
          <StatusChart data={chartData} />
        </div>
      )}

      <div className="ac-card">
        <div className="ac-details-header">
          <div className="ac-details-title-group">
            <h2>Investigation Details</h2>
            <p>{summary.total_investigations} investigations total</p>
          </div>
          <div className="ac-filters">
            <FilterSelect
              value={siteFilter}
              onChange={(v) => {
                setSiteFilter(v);
                setPage(1);
              }}
              defaultLabel="All Sites"
              options={summary.filter_options.sites}
            />
            <FilterSelect
              value={deptFilter}
              onChange={(v) => {
                setDeptFilter(v);
                setPage(1);
              }}
              defaultLabel="Dept"
              options={summary.filter_options.departments}
            />
            <FilterSelect
              value={productFilter}
              onChange={(v) => {
                setProductFilter(v);
                setPage(1);
              }}
              defaultLabel="Product"
              options={summary.filter_options.products}
            />
            <FilterSelect
              value={investigatorFilter}
              onChange={(v) => {
                setInvestigatorFilter(v);
                setPage(1);
              }}
              defaultLabel="All Investigators"
              options={summary.filter_options.investigators}
            />
            <FilterSelect
              value={startPreset}
              onChange={(v) => {
                setStartPreset(v);
                setPage(1);
              }}
              defaultLabel="All Time (Start Date)"
              options={["7", "30", "180"]}
              formatOption={(v) => (v === "7" ? "Last week" : v === "30" ? "Last month" : "Last 6 months")}
            />
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
                <th>Event Type</th>
                <th>Investigator</th>
                <th>Progress</th>
                <th>Start Date</th>
                <th>Due Date</th>
                <th>Status</th>
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
                    <td>
                      <span className={`status-pill ${statusInfo.status}`}>{statusInfo.label}</span>
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
              <span key={`ellipsis-${idx}`} style={{ fontSize: 14, color: "var(--color-text-muted)", padding: "0 4px" }}>
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
