import { HorizontalBarChart } from "../components/charts/HorizontalBarChart";
import { VerticalBarChart } from "../components/charts/VerticalBarChart";
import { LineChart } from "../components/charts/LineChart";
import { Gauge } from "../components/charts/Gauge";
import "./AnalyticsPage.css";

// Matches the approved Figma "Analytics" dashboard (rail icon 3, node
// 1229:41868 — sub-sections: Event 1229:41892, Root Cause Status 1252:25454,
// CAPA Status 1229:42279, Investigation Quality 1229:42536, Failure Pattern
// Analysis 1229:43167). MOCK DATA throughout — this reporting dashboard has
// no backend yet; numbers mirror the approved Figma content exactly so the
// layout can be reviewed.

const FilterPill = ({ label }: { label: string }) => (
  <span className="an-filter-pill">
    {label} <span aria-hidden>▾</span>
  </span>
);

// ── Event section ──────────────────────────────────────────────────────────

const EVENT_CARDS = [
  { eyebrow: "OVERALL LOGGED", total: 342, inProgress: 87, closed: 255, trend: -12.3, overdue: 18, overduePct: 23 },
  { eyebrow: "DEVIATION", total: 156, inProgress: 42, closed: 114, trend: -8.4, overdue: 6, overduePct: 15 },
  { eyebrow: "OOS", total: 89, inProgress: 23, closed: 66, trend: 5.2, overdue: 5, overduePct: 24 },
  { eyebrow: "OOT", total: 64, inProgress: 15, closed: 49, trend: 3.1, overdue: 4, overduePct: 27 },
  { eyebrow: "MARKET COMPLAINT", total: 33, inProgress: 7, closed: 26, trend: -15.6, overdue: 3, overduePct: 46 },
];

function EventSection() {
  return (
    <section className="an-section">
      <div className="an-section-header">
        <p className="an-section-title">Event</p>
        <div className="an-filters">
          <FilterPill label="All Sites" />
          <FilterPill label="Dept" />
          <FilterPill label="Product" />
          <FilterPill label="Last 30 days" />
        </div>
      </div>
      <div className="an-grid" style={{ gridTemplateColumns: "repeat(5, 1fr)" }}>
        {EVENT_CARDS.map((c) => {
          const isGood = c.trend > 0;
          return (
            <div className="an-card" key={c.eyebrow}>
              <p className="an-card-eyebrow">{c.eyebrow}</p>
              <p className="an-card-big-number">{c.total}</p>
              <div className="an-card-subrow">
                <div>
                  <p className="label">In Progress</p>
                  <p className="value">{c.inProgress}</p>
                </div>
                <div style={{ textAlign: "right" }}>
                  <p className="label">Closed</p>
                  <p className="value">{c.closed}</p>
                </div>
              </div>
              <p className={`an-trend ${isGood ? "up-good" : "up-bad"}`}>
                {Math.abs(c.trend)}% vs Last month
              </p>
              <div className="an-card-subrow" style={{ borderTop: "1px solid var(--color-card-border)", paddingTop: 9 }}>
                <span className="label" style={{ fontWeight: 700, color: "var(--color-text-muted)" }}>OVERDUE</span>
                <span style={{ color: "var(--color-danger-text)", fontWeight: 700, fontSize: 16 }}>{c.overdue}</span>
              </div>
              <div className="an-progress-track">
                <div className="an-progress-fill" style={{ width: `${c.overduePct}%`, background: "var(--color-danger-text)" }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ── Root Cause Status section ──────────────────────────────────────────────

const RC_STATUS_CARDS = [
  { key: "good", label: "ROOT CAUSE IDENTIFIED", value: 133, total: 255, trend: 2.4, pct: 52 },
  { key: "warn", label: "PROBABLE ROOT CAUSE", value: 78, total: 255, trend: 5.6, pct: 31 },
  { key: "bad", label: "NO ROOT CAUSE", value: 44, total: 255, trend: -9.1, pct: 17 },
] as const;

const RC_CATEGORY_ROWS = [
  { label: "Method", value: 30, secondaryValue: 28 },
  { label: "Material", value: 24, secondaryValue: 26 },
  { label: "Measurement", value: 13, secondaryValue: 13 },
  { label: "Mother Nature", value: 13, secondaryValue: 20 },
  { label: "Man", value: 15, secondaryValue: 15 },
  { label: "Machine", value: 18, secondaryValue: 15 },
];

function RootCauseStatusSection() {
  return (
    <section className="an-section">
      <div className="an-section-header">
        <div>
          <span className="an-section-title">Root Cause Status</span>
          <span className="an-section-subtitle">— 255 closed events</span>
        </div>
        <div className="an-filters">
          <FilterPill label="All Dept" />
          <FilterPill label="All Product" />
          <FilterPill label="June 2026" />
          <span className="an-tab">Monthly Trends</span>
          <span className="an-tab active">6M Analysis</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 12, alignItems: "stretch" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {RC_STATUS_CARDS.map((c) => (
            <div className={`an-status-card ${c.key}`} key={c.label}>
              <div className="an-status-card-header">{c.label}</div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span className="an-status-card-number">
                  {c.value}
                  <span style={{ fontSize: 16, fontWeight: 500, color: "var(--color-text-muted)" }}>/{c.total}</span>
                </span>
                <span className="an-badge">{c.trend > 0 ? "↗" : "↘"}{Math.abs(c.trend)}%</span>
              </div>
              <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>{c.pct}% of total closed</p>
              <div className="an-progress-track">
                <div
                  className="an-progress-fill"
                  style={{ width: `${c.pct}%`, background: c.key === "good" ? "var(--color-success-text)" : c.key === "warn" ? "var(--color-warning-text)" : "var(--color-danger-text)" }}
                />
              </div>
            </div>
          ))}
        </div>

        <div className="an-card" style={{ gap: 12 }}>
          <div className="an-card-subrow">
            <p style={{ margin: 0, fontSize: 13, fontWeight: 700, letterSpacing: "0.03em", color: "var(--color-text-muted)" }}>
              6M ANALYSIS — ROOT CAUSE BY CAUSE CATEGORY
            </p>
          </div>
          <div className="an-tabs">
            <span className="an-tab active">All</span>
            <span className="an-tab">Deviation</span>
            <span className="an-tab">OOS</span>
            <span className="an-tab">OOT</span>
            <span className="an-tab">Market Complaint</span>
          </div>
          <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>Man · Machine · Material · Method · Measurement · Mother Nature</p>
          <HorizontalBarChart rows={RC_CATEGORY_ROWS} maxValue={80} primaryColor="#22c55e" secondaryColor="#f59e0b" legend={{ primary: "With RC", secondary: "Probable RC" }} />
          <div className="an-note info">
            <strong>Observation:</strong> Method is the most frequent root cause category with 78 events. Root cause identification rate is strong in this category.
          </div>
        </div>
      </div>
    </section>
  );
}

// ── CAPA Status section ─────────────────────────────────────────────────────

const CAPA_MONTHLY_TREND = [
  { label: "Jan", value: 270 },
  { label: "Feb", value: 140 },
  { label: "Mar", value: 205 },
  { label: "Apr", value: 120 },
  { label: "May", value: 250 },
  { label: "Jun", value: 205 },
];

const CAPA_RANKING_ROWS = [
  { tier: "L5", color: "#a855f7", label: "Error Proofing", description: "Poka-yoke / design change prevents error", hierarchy: "Highest Hierarchy", value: 29 },
  { tier: "L4", color: "#3b82f6", label: "Error Prevention", description: "Process / system redesign prevents recurrence", hierarchy: "High Hierarchy", value: 55 },
  { tier: "L3", color: "#14b8a6", label: "Detection by Technology", description: "Automated detection system catches error", hierarchy: "Medium Hierarchy", value: 27 },
  { tier: "L2", color: "#f97316", label: "Detection by Human", description: "Human intervention detects the error", hierarchy: "Low Hierarchy", value: 63 },
  { tier: "L1", color: "#ef4444", label: "Not Mandatory", description: "CAPA not required for this event type", hierarchy: "Lowest Hierarchy", value: 34 },
];

function CapaStatusSection() {
  const maxRanking = Math.max(...CAPA_RANKING_ROWS.map((r) => r.value));
  return (
    <section className="an-section">
      <div className="an-section-header">
        <div>
          <span className="an-section-title">CAPA Status</span>
          <span className="an-section-subtitle">— 255 closed events</span>
        </div>
        <div className="an-filters">
          <FilterPill label="All Dept" />
          <FilterPill label="All Product" />
          <FilterPill label="June 2026" />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="an-status-card good">
            <div className="an-status-card-header">WITH CAPA</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span className="an-status-card-number">209</span>
              <span className="an-badge">↗6.2%</span>
            </div>
            <div className="an-progress-track">
              <div className="an-progress-fill" style={{ width: "82%", background: "var(--color-success-text)" }} />
            </div>
            <div className="an-card-subrow">
              <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>82% of total closed</span>
              <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>15% CAPA reused</span>
            </div>
          </div>
          <div className="an-status-card warn">
            <div className="an-status-card-header">WITHOUT CAPA</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span className="an-status-card-number">46</span>
              <span className="an-badge" style={{ background: "var(--color-danger-bg)", color: "var(--color-danger-text)" }}>↘5.4%</span>
            </div>
            <div className="an-progress-track">
              <div className="an-progress-fill" style={{ width: "18%", background: "var(--color-warning-text)" }} />
            </div>
            <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>18% of total closed</p>
          </div>
          <div className="an-card">
            <div className="an-card-subrow">
              <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "var(--color-text-muted)" }}>MONTHLY TREND</p>
              <span className="an-badge">✓ WITH CAPA</span>
            </div>
            <VerticalBarChart data={CAPA_MONTHLY_TREND} color="#00786f" />
          </div>
        </div>

        <div className="an-card" style={{ gap: 16 }}>
          <p style={{ margin: 0, fontWeight: 700, fontSize: 14, color: "var(--color-text-muted)" }}>CAPA RANKING BREAKDOWN</p>
          {CAPA_RANKING_ROWS.map((row) => (
            <div key={row.tier} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span
                style={{
                  background: row.color,
                  color: "#fff",
                  width: 28,
                  height: 28,
                  borderRadius: 6,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 12,
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                {row.tier}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="an-card-subrow">
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{row.label}</span>
                  <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{row.hierarchy}</span>
                </div>
                <p style={{ margin: "2px 0 6px", fontSize: 12, color: "var(--color-text-muted)" }}>{row.description}</p>
                <div className="an-progress-track">
                  <div className="an-progress-fill" style={{ width: `${(row.value / maxRanking) * 100}%`, background: row.color }} />
                </div>
              </div>
              <span style={{ fontWeight: 700, fontSize: 16, width: 24, textAlign: "right" }}>{row.value}</span>
            </div>
          ))}
          <div className="an-note warn">
            <strong>Observation:</strong> 30% of CAPAs are Level 2 (Detection by Human). Majority CAPAs rely on human detection. Invest in process redesign to reduce recurrence risk.
          </div>
        </div>
      </div>
    </section>
  );
}

// ── Investigation Quality (IQ Score) section ────────────────────────────────

const INVESTIGATORS = [
  { initials: "RK", color: "#0d9488", name: "Rajesh Kurian", tag: "TOP", score: 93, trend: 6.6, events: 35, overdue: 3, assignable: 28 },
  { initials: "D", color: "#f97316", name: "Darshan", tag: null, score: 83, trend: 4.6, events: 17, overdue: 3, assignable: 12 },
  { initials: "G", color: "#22c55e", name: "Gurubaswaraj", tag: null, score: 81, trend: -2.4, events: 23, overdue: 6, assignable: 17 },
  { initials: "KN", color: "#a855f7", name: "Kiran NV", tag: null, score: 70, trend: -0.6, events: 20, overdue: 5, assignable: 14 },
  { initials: "AP", color: "#3b82f6", name: "Abhijit Patil", tag: null, score: 70, trend: 6.8, events: 19, overdue: 5, assignable: 15 },
  { initials: "A", color: "#ef4444", name: "Anirudhha", tag: null, score: 68, trend: -1, events: 22, overdue: 6, assignable: 17 },
];

const TOP_PERFORMANCE_HISTORY = [
  { month: "Jun", initials: "RK", color: "#f59e0b", name: "Rajesh Kurian", score: 100 },
  { month: "May", initials: "D", color: "#3b82f6", name: "Darshan", score: 100 },
  { month: "Apr", initials: "GB", color: "#22c55e", name: "Gurubaswaraj", score: 96 },
  { month: "Mar", initials: "KV", color: "#a855f7", name: "Kiran NV", score: 98 },
  { month: "Feb", initials: "AP", color: "#3b82f6", name: "Abhijit Patil", score: 94 },
  { month: "Jan", initials: "A", color: "#ef4444", name: "Anirudhha", score: 94 },
  { month: "Dec", initials: "GB", color: "#f59e0b", name: "Giribabu", score: 100 },
  { month: "Nov", initials: "V", color: "#22c55e", name: "Visalachi", score: 100 },
];

const BOTTOM_5 = [
  { month: "Jun", initials: "KR", color: "#ef4444", name: "Visalachi", score: 68 },
  { month: "May", initials: "PM", color: "#a855f7", name: "Darshan", score: 69 },
  { month: "Apr", initials: "TR", color: "#f59e0b", name: "Gurubaswaraj", score: 70 },
  { month: "Mar", initials: "RU", color: "#3b82f6", name: "Kiran NV", score: 71 },
  { month: "Feb", initials: "LG", color: "#22c55e", name: "Abhijit Patel", score: 72 },
  { month: "Jan", initials: "CA", color: "#ef4444", name: "Anirudhha", score: 73 },
  { month: "Dec", initials: "HD", color: "#3b82f6", name: "Giribabu", score: 74 },
  { month: "Nov", initials: "NP", color: "#f59e0b", name: "Rajesh Kurian", score: 75 },
];

const IQ_TREND_SERIES = [
  { name: "Rajesh Kurian", color: "#0d9488", values: [95, 100, 96, 99, 94, 100] },
  { name: "Darshan", color: "#3b82f6", values: [85, 88, 90, 87, 91, 88] },
  { name: "Gurubasawaraj", color: "#f59e0b", values: [78, 82, 90, 83, 79, 90] },
  { name: "Kiran NV", color: "#22c55e", values: [75, 78, 80, 78, 82, 79] },
  { name: "Aniruddha", color: "#a855f7", values: [70, 65, 75, 68, 70, 68] },
];

const CLOSURE_RATE = [
  { label: "Jan", value: 7.5 },
  { label: "Feb", value: 4.7 },
  { label: "Mar", value: 5.5 },
  { label: "Apr", value: 4.2 },
  { label: "May", value: 7.2 },
  { label: "Jun", value: 6.3 },
];

function InvestigationQualitySection() {
  return (
    <section className="an-section">
      <div className="an-section-header">
        <span className="an-section-title">Investigation Quality (IQ Score)</span>
        <div className="an-filters">
          <FilterPill label="All Dept" />
          <FilterPill label="All Product" />
          <FilterPill label="June 2026" />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 12 }}>
        <div className="an-card" style={{ background: "var(--color-warning-bg)", alignItems: "center", justifyContent: "center", textAlign: "center", gap: 16 }}>
          <p style={{ margin: 0, fontSize: 12, fontWeight: 700, letterSpacing: "0.05em", color: "var(--color-warning-text)" }}>PLANT IQ SCORE</p>
          <div style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Gauge value={78} max={100} size={110} color="var(--color-warning-text)" trackColor="var(--color-warning-border)" />
            <div style={{ position: "absolute", display: "flex", flexDirection: "column", alignItems: "center" }}>
              <span style={{ fontSize: 32, fontWeight: 700, color: "var(--color-warning-text)" }}>78</span>
              <span style={{ fontSize: 11, color: "var(--color-warning-text)" }}>out of 100</span>
            </div>
          </div>
          <p style={{ margin: 0, fontSize: 12, color: "var(--color-warning-text)" }}>△ Near target</p>
          <div style={{ display: "flex", gap: 12, width: "100%" }}>
            <div style={{ flex: 1, background: "var(--color-surface)", border: "1px solid var(--color-card-border)", borderRadius: 8, padding: 10 }}>
              <p style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>6</p>
              <p style={{ margin: 0, fontSize: 10, color: "var(--color-text-muted)", textTransform: "uppercase" }}>Investigators</p>
            </div>
            <div style={{ flex: 1, background: "var(--color-surface)", border: "1px solid var(--color-card-border)", borderRadius: 8, padding: 10 }}>
              <p style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>136</p>
              <p style={{ margin: 0, fontSize: 10, color: "var(--color-text-muted)", textTransform: "uppercase" }}>Total Cases</p>
            </div>
          </div>
        </div>

        <div className="an-card">
          <p style={{ margin: 0, fontWeight: 700, fontSize: 14, color: "var(--color-text-muted)" }}>ALL INVESTIGATORS</p>
          {INVESTIGATORS.map((inv) => {
            const isGood = inv.trend > 0;
            return (
              <div className="an-leaderboard-row" key={inv.name}>
                <span className="an-avatar" style={{ background: inv.color }}>{inv.initials}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="an-card-subrow">
                    <span style={{ fontWeight: 600, fontSize: 14 }}>
                      {inv.name} <span style={{ color: "var(--color-text-muted)", fontWeight: 400 }}>(QC)</span>
                      {inv.tag && <span className="an-badge" style={{ marginLeft: 6 }}>{inv.tag}</span>}
                    </span>
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontWeight: 700 }}>{inv.score}</span>
                      <span className={`an-trend ${isGood ? "up-good" : "up-bad"}`}>{isGood ? "↗" : "↘"}{Math.abs(inv.trend)}%</span>
                    </span>
                  </div>
                  <div className="an-progress-track" style={{ marginTop: 4 }}>
                    <div className="an-progress-fill" style={{ width: `${inv.score}%`, background: inv.score === Math.min(...INVESTIGATORS.map((i) => i.score)) ? "var(--color-warning-text)" : "var(--color-info-text)" }} />
                  </div>
                  <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--color-text-muted)" }}>
                    {inv.events} Events · <span style={{ color: "var(--color-danger-text)" }}>{inv.overdue} overdue</span> · {inv.assignable} Assignable RC
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="an-card">
            <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "var(--color-text-muted)" }}>TOP PERFORMANCE HISTORY</p>
            <table className="an-table">
              <tbody>
                {TOP_PERFORMANCE_HISTORY.map((row) => (
                  <tr key={row.month + row.name}>
                    <td style={{ color: "var(--color-text-muted)", width: 32 }}>{row.month}</td>
                    <td style={{ width: 32 }}>
                      <span className="an-avatar" style={{ background: row.color, width: 24, height: 24, fontSize: 10 }}>{row.initials}</span>
                    </td>
                    <td>{row.name}</td>
                    <td style={{ textAlign: "right", fontWeight: 700 }}>{row.score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="an-card">
            <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "var(--color-text-muted)" }}>BOTTOM 5</p>
            <table className="an-table">
              <tbody>
                {BOTTOM_5.map((row) => (
                  <tr key={row.month + row.name}>
                    <td style={{ color: "var(--color-text-muted)", width: 32 }}>{row.month}</td>
                    <td style={{ width: 32 }}>
                      <span className="an-avatar" style={{ background: row.color, width: 24, height: 24, fontSize: 10 }}>{row.initials}</span>
                    </td>
                    <td>{row.name}</td>
                    <td style={{ textAlign: "right", fontWeight: 700 }}>{row.score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="an-card" style={{ background: "var(--color-success-bg)", border: "1px solid var(--color-success-border)" }}>
            <div className="an-card-subrow">
              <span style={{ fontWeight: 700, fontSize: 13, color: "var(--color-success-text)" }}>👑 TOP PERFORMER — OVERALL</span>
              <span style={{ fontSize: 12, color: "var(--color-success-text)" }}>Highest IQ Score</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span className="an-avatar" style={{ background: "#0d9488", width: 44, height: 44, fontSize: 16 }}>AV</span>
              <div>
                <p style={{ margin: 0, fontWeight: 700, fontSize: 16 }}>Rajesh Kurian</p>
                <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>QA</p>
                <p style={{ margin: 0, fontSize: 20, fontWeight: 700, color: "var(--color-success-text)" }}>93 <span style={{ fontSize: 13 }}>↗6.6%</span></p>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              {[["35", "CASES"], ["15", "ACTIVE"], ["30", "CAPA CLOSED"], ["28", "RC IDENTIFIED"], ["2d 20h", "AVG CLOSE TIME"]].map(([n, l]) => (
                <div key={l} style={{ flex: 1, background: "var(--color-surface)", borderRadius: 8, padding: 8, textAlign: "center" }}>
                  <p style={{ margin: 0, fontWeight: 700, fontSize: 14 }}>{n}</p>
                  <p style={{ margin: 0, fontSize: 9, color: "var(--color-text-muted)" }}>{l}</p>
                </div>
              ))}
            </div>
            <div className="an-note" style={{ background: "var(--color-surface)", border: "none", color: "var(--color-success-text)" }}>
              <strong>Strength:</strong> Consistently strong documentation, high RC identification rate (80%), and timely closures.
            </div>
          </div>

          <div className="an-card" style={{ background: "var(--color-danger-bg)", border: "1px solid var(--color-danger-border)" }}>
            <div className="an-card-subrow">
              <span style={{ fontWeight: 700, fontSize: 13, color: "var(--color-danger-text)" }}>⬆ NEEDS IMPROVEMENT</span>
              <span style={{ fontSize: 12, color: "var(--color-danger-text)" }}>Lowest IQ Score</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span className="an-avatar" style={{ background: "#ef4444", width: 44, height: 44, fontSize: 16 }}>KR</span>
              <div>
                <p style={{ margin: 0, fontWeight: 700, fontSize: 16 }}>Visalachi</p>
                <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>QC OOS</p>
                <p style={{ margin: 0, fontSize: 20, fontWeight: 700, color: "var(--color-danger-text)" }}>68 <span style={{ fontSize: 13 }}>↘1%</span></p>
              </div>
            </div>
            <p style={{ margin: 0, fontWeight: 700, fontSize: 12, color: "var(--color-danger-text)" }}>AREAS OF IMPROVEMENT</p>
            <div className="an-note" style={{ background: "var(--color-surface)", border: "none", color: "var(--color-text)" }}>
              › Reduce overdue investigations — 6 of 22 cases past due date
            </div>
            <div className="an-note warn">
              <strong>Action:</strong> Schedule a 1-on-1 coaching session and assign a peer mentor from the top performer group.
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div className="an-card">
          <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "var(--color-text-muted)" }}>MONTHLY IQ SCORE TRENDS — ALL INVESTIGATORS</p>
          <LineChart categories={["Jan", "Feb", "Mar", "Apr", "May", "Jun"]} series={IQ_TREND_SERIES} yMin={40} yMax={100} />
          <div className="an-note warn">
            <strong>Observation:</strong> Plant IQ at 78. Gap between top (Rajesh Kurian: 93) and bottom (Aniruddha: 68) is 25 points. Significant spread — structured knowledge transfer recommended.
          </div>
        </div>
        <div className="an-card">
          <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "var(--color-text-muted)" }}>AVG. INVESTIGATION CLOSURE RATE</p>
          <VerticalBarChart data={CLOSURE_RATE} color="#00786f" yLabel="Days" />
          <div className="an-note warn">
            <strong>Observation:</strong> Most number of investigation has been closed in Jan 2026 where Rajesh Kurian has closed 35 investigations and Kavita has closed 12.
          </div>
        </div>
      </div>
    </section>
  );
}

// ── Failure Pattern Analysis section ────────────────────────────────────────

const PRODUCT_FREQUENCY = [
  { label: "Metformin", value: 47 },
  { label: "Paracetamol", value: 28 },
  { label: "Cetirizine", value: 21 },
  { label: "Azithromycin", value: 26 },
  { label: "Omeprazole", value: 23 },
  { label: "Ibuprofen", value: 15 },
  { label: "Amoxicillin", value: 14 },
  { label: "Atorvastatin", value: 6 },
];

const EQUIPMENT_FREQUENCY = [
  { label: "Blender BLD-01", value: 34 },
  { label: "Dissolution DS-06", value: 30 },
  { label: "Autoclave AC-07", value: 26 },
  { label: "Tablet Press 03", value: 28 },
  { label: "Granulator GRN-02", value: 22 },
  { label: "Coating Pan CP-04", value: 14 },
  { label: "Filling Line FL-08", value: 13 },
  { label: "HPLC Unit 05", value: 12 },
];

const RECURRING_FAILURES = [
  { category: "Equipment", color: "#ef4444", count: 29, description: "Process parameters not validated for current equipment state" },
  { category: "Measurement", color: "#f97316", count: 13, description: "Instrument calibration affected by temperature fluctuations" },
  { category: "Human", color: "#eab308", count: 13, description: "Sampling errors linked to material lot variation" },
  { category: "Material", color: "#3b82f6", count: 6, description: "SOP not aligned with raw material variability" },
  { category: "Equipment", color: "#3b82f6", count: 4, description: "Operator training gap on critical equipment" },
];

const FAILURE_TREND_SERIES = [
  { name: "Metformin", color: "#ef4444", values: [37, 52, 46, 47, 44, 53] },
  { name: "Blender", color: "#f97316", values: [29, 31, 44, 38, 33, 33] },
  { name: "Patterns", color: "#a855f7", values: [20, 21, 34, 28, 27, 29] },
];

function FailurePatternSection() {
  return (
    <section className="an-section alert">
      <div className="an-section-header">
        <div>
          <span className="an-section-title">Failure Pattern Analysis</span>
          <span className="an-section-subtitle">— recurring patterns and grey areas</span>
        </div>
        <div className="an-filters">
          <FilterPill label="All Dept" />
          <FilterPill label="All Product" />
          <FilterPill label="All Equipment" />
          <FilterPill label="June 2026" />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div className="an-card">
          <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "var(--color-text-muted)" }}>PRODUCTS — DEVIATION FREQUENCY</p>
          <HorizontalBarChart rows={PRODUCT_FREQUENCY} maxValue={80} primaryColor="#0d9488" />
          <div className="an-note bad">
            <strong>Grey Area:</strong> Metformin 1000mg has highest deviation count (47). Prioritise process review for this product line.
          </div>
        </div>
        <div className="an-card">
          <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "var(--color-text-muted)" }}>EQUIPMENT — ERROR &amp; BREAKDOWN FREQUENCY</p>
          <HorizontalBarChart rows={EQUIPMENT_FREQUENCY} maxValue={60} primaryColor="#0d9488" />
          <div className="an-note warn">
            <strong>Grey Area:</strong> Blender BLD-01 leads with 34 errors. Schedule preventive maintenance and calibration review.
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div className="an-card">
          <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "var(--color-text-muted)" }}>RECURRING FAILURE</p>
          {RECURRING_FAILURES.map((row, i) => (
            <div className="an-recurring-row" key={i}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: row.color, marginTop: 6, flexShrink: 0 }} />
                <div>
                  <p style={{ margin: 0, fontWeight: 600, fontSize: 14 }}>{row.category}</p>
                  <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)", fontStyle: "italic" }}>💡 {row.description}</p>
                </div>
              </div>
              <span className="an-badge" style={{ background: "#fef2f2", color: "#dc2626", flexShrink: 0 }}>{row.count} events</span>
            </div>
          ))}
        </div>
        <div className="an-card">
          <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "var(--color-text-muted)" }}>MONTHLY TRENDS — TOP FAILURES</p>
          <LineChart categories={["Jan", "Feb", "Mar", "Apr", "May", "Jun"]} series={FAILURE_TREND_SERIES} yMin={0} yMax={60} />
          <div className="an-note warn">
            <strong>Pattern:</strong> Metformin failures and Blender errors show correlated spikes — investigate shared process parameters.
          </div>
        </div>
      </div>
    </section>
  );
}

export function AnalyticsPage() {
  return (
    <div className="an-page">
      <EventSection />
      <RootCauseStatusSection />
      <CapaStatusSection />
      <InvestigationQualitySection />
      <FailurePatternSection />
    </div>
  );
}
