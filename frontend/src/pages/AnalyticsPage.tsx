import { useEffect, useState } from "react";
import { HorizontalBarChart } from "../components/charts/HorizontalBarChart";
import { VerticalBarChart } from "../components/charts/VerticalBarChart";
import { LineChart } from "../components/charts/LineChart";
import { Gauge } from "../components/charts/Gauge";
import { FilterSelect } from "../components/FilterSelect";
import { ApiError } from "../api/client";
import {
  getAnalyticsSummary,
  type AnalyticsSummaryResponse,
  type CapaStatusResponse,
  type CategoryCountResponse,
  type EventTypeCardResponse,
  type FailurePatternsResponse,
  type RootCauseStatusResponse,
} from "../api/dashboard";
import "./AnalyticsPage.css";

// Matches the approved Figma "Analytics" dashboard (rail icon 3, node
// 1229:41868 — sub-sections: Event 1229:41892, Root Cause Status 1252:25454,
// CAPA Status 1229:42279, Investigation Quality 1229:42536, Failure Pattern
// Analysis 1229:43167).
//
// Real-data pass (2026-08-03), per the user — only sections that map
// cleanly onto real star-schema columns are wired: Event, CAPA presence,
// Root Cause presence, and Failure Pattern product/equipment frequency (see
// backend/routers/analytics.py's module docstring). Investigation Quality
// (IQ Score), the CAPA L1-L5 hierarchy ranking, and the Failure Pattern
// "Recurring Failure" narrative cards + monthly trend line chart have no
// backing data/formula anywhere in the star schema and are STILL MOCK DATA
// — clearly commented at each remaining mock block below.

const FilterPill = ({ label }: { label: string }) => (
  <span className="an-filter-pill">
    {label} <span aria-hidden>▾</span>
  </span>
);

function fmtTrend(trend: number | null): { text: string; isGood: boolean } {
  if (trend === null) return { text: "No data last month", isGood: true };
  return { text: `${Math.abs(trend)}% vs Last month`, isGood: trend > 0 };
}

// ── Event section ──────────────────────────────────────────────────────────

function EventSection({ events }: { events: EventTypeCardResponse[] }) {
  return (
    <section className="an-section">
      <div className="an-section-header">
        <p className="an-section-title">Event</p>
      </div>
      <div className="an-grid" style={{ gridTemplateColumns: "repeat(5, 1fr)" }}>
        {events.map((c) => {
          const trend = fmtTrend(c.trend_pct);
          return (
            <div className="an-card" key={c.key}>
              <p className="an-card-eyebrow">{c.label}</p>
              <p className="an-card-big-number">{c.total}</p>
              <div className="an-card-subrow">
                <div>
                  <p className="label">In Progress</p>
                  <p className="value">{c.in_progress}</p>
                </div>
                <div style={{ textAlign: "right" }}>
                  <p className="label">Closed</p>
                  <p className="value">{c.closed}</p>
                </div>
              </div>
              <p className={`an-trend ${trend.isGood ? "up-good" : "up-bad"}`}>{trend.text}</p>
              <div className="an-card-subrow" style={{ borderTop: "1px solid var(--color-card-border)", paddingTop: 9 }}>
                <span className="label" style={{ fontWeight: 700, color: "var(--color-text-muted)" }}>OVERDUE</span>
                <span style={{ color: "var(--color-danger-text)", fontWeight: 700, fontSize: 16 }}>{c.overdue}</span>
              </div>
              <div className="an-progress-track">
                <div className="an-progress-fill" style={{ width: `${c.overdue_pct}%`, background: "var(--color-danger-text)" }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ── Root Cause Status section ──────────────────────────────────────────────

function RootCauseStatusSection({
  status,
  categories,
}: {
  status: RootCauseStatusResponse;
  categories: CategoryCountResponse[];
}) {
  // Only a 2-way split (Identified / Not Identified) — real data has no
  // column distinguishing "confirmed" from "probable" root cause, so the
  // original Figma mock's 3-tier split isn't reproducible with real data.
  const identifiedPct = status.total ? Math.round((status.identified / status.total) * 100) : 0;
  const cards = [
    { key: "good", label: "ROOT CAUSE IDENTIFIED", value: status.identified, pct: identifiedPct },
    { key: "bad", label: "NO ROOT CAUSE", value: status.not_identified, pct: 100 - identifiedPct },
  ] as const;

  const maxCategory = Math.max(...categories.map((c) => c.count), 1);

  return (
    <section className="an-section">
      <div className="an-section-header">
        <div>
          <span className="an-section-title">Root Cause Status</span>
          <span className="an-section-subtitle">— {status.total} events</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 12, alignItems: "stretch" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {cards.map((c) => (
            <div className={`an-status-card ${c.key}`} key={c.label}>
              <div className="an-status-card-header">{c.label}</div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span className="an-status-card-number">
                  {c.value}
                  <span style={{ fontSize: 16, fontWeight: 500, color: "var(--color-text-muted)" }}>/{status.total}</span>
                </span>
              </div>
              <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>{c.pct}% of total</p>
              <div className="an-progress-track">
                <div
                  className="an-progress-fill"
                  style={{ width: `${c.pct}%`, background: c.key === "good" ? "var(--color-success-text)" : "var(--color-danger-text)" }}
                />
              </div>
            </div>
          ))}
        </div>

        <div className="an-card" style={{ gap: 12 }}>
          <div className="an-card-subrow">
            <p style={{ margin: 0, fontSize: 13, fontWeight: 700, letterSpacing: "0.03em", color: "var(--color-text-muted)" }}>
              ROOT CAUSE BY CAUSE CATEGORY
            </p>
          </div>
          {/* Best-effort mapping of real root_cause_category values onto the
              Man/Machine/Material/Method/Measurement/Mother Nature scheme —
              real data doesn't actually follow a 6M taxonomy (see
              backend/routers/analytics.py's _ROOT_CAUSE_TO_6M for the exact
              mapping and its limits); events with no clear-fit category are
              excluded from this chart rather than forced into a bucket. */}
          <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>Man · Machine · Material · Method · Measurement · Mother Nature</p>
          <HorizontalBarChart rows={categories.map((c) => ({ label: c.label, value: c.count }))} maxValue={maxCategory} primaryColor="#22c55e" />
        </div>
      </div>
    </section>
  );
}

// ── CAPA Status section ─────────────────────────────────────────────────────

function CapaStatusSection({ capa }: { capa: CapaStatusResponse }) {
  const withPct = capa.total ? Math.round((capa.with_capa / capa.total) * 100) : 0;
  const withoutPct = 100 - withPct;
  const maxCategory = Math.max(...capa.by_root_cause_category.map((c) => c.count), 1);

  return (
    <section className="an-section">
      <div className="an-section-header">
        <div>
          <span className="an-section-title">CAPA Status</span>
          <span className="an-section-subtitle">— {capa.total} events</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="an-status-card good">
            <div className="an-status-card-header">WITH CAPA</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span className="an-status-card-number">{capa.with_capa}</span>
            </div>
            <div className="an-progress-track">
              <div className="an-progress-fill" style={{ width: `${withPct}%`, background: "var(--color-success-text)" }} />
            </div>
            <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>{withPct}% of total events</p>
          </div>
          <div className="an-status-card warn">
            <div className="an-status-card-header">WITHOUT CAPA</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span className="an-status-card-number">{capa.without_capa}</span>
            </div>
            <div className="an-progress-track">
              <div className="an-progress-fill" style={{ width: `${withoutPct}%`, background: "var(--color-warning-text)" }} />
            </div>
            <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>{withoutPct}% of total events</p>
          </div>
          <div className="an-card">
            <div className="an-card-subrow">
              <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "var(--color-text-muted)" }}>MONTHLY TREND</p>
              <span className="an-badge">✓ WITH CAPA</span>
            </div>
            <VerticalBarChart data={capa.monthly_trend.map((m) => ({ label: m.label, value: m.value }))} color="#00786f" />
          </div>
        </div>

        <div className="an-card" style={{ gap: 16 }}>
          {/* Replaces the mock's L1-L5 hierarchy ranking (Error Proofing /
              Error Prevention / ...) — capa_effectiveness is 100% NULL on the
              live DB and no other column encodes a CAPA hierarchy tier
              anywhere in the star schema. This shows which root-cause
              categories the CAPA'd events actually fall under instead — a
              real, groundable substitute (see backend/routers/analytics.py). */}
          <p style={{ margin: 0, fontWeight: 700, fontSize: 14, color: "var(--color-text-muted)" }}>CAPA'D EVENTS BY ROOT CAUSE CATEGORY</p>
          {capa.by_root_cause_category.map((row) => (
            <div key={row.label} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="an-card-subrow">
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{row.label}</span>
                </div>
                <div className="an-progress-track" style={{ marginTop: 6 }}>
                  <div className="an-progress-fill" style={{ width: `${(row.count / maxCategory) * 100}%`, background: "#00786f" }} />
                </div>
              </div>
              <span style={{ fontWeight: 700, fontSize: 16, width: 40, textAlign: "right" }}>{row.count}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Investigation Quality (IQ Score) section ────────────────────────────────
// STILL MOCK DATA — no IQ Score formula exists anywhere in this codebase or
// the star schema; computing a real one is a product/business-logic decision
// deferred per the user (2026-08-03), not a data-availability gap like the
// sections above. Revisit once that formula is defined.

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
// Product/equipment frequency below is real (failure_patterns prop). The
// "Recurring Failure" cards and "Monthly Trends" line chart are STILL MOCK
// DATA — they need narrative descriptions and time-series granularity this
// pass deliberately didn't build (out of the agreed data-groundable scope,
// see AnalyticsPage's top-of-file comment).

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

function FailurePatternSection({ patterns }: { patterns: FailurePatternsResponse }) {
  const maxProduct = Math.max(...patterns.products.map((p) => p.value), 1);
  const maxEquipment = Math.max(...patterns.equipment.map((e) => e.value), 1);
  return (
    <section className="an-section alert">
      <div className="an-section-header">
        <div>
          <span className="an-section-title">Failure Pattern Analysis</span>
          <span className="an-section-subtitle">— recurring patterns and grey areas</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div className="an-card">
          <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "var(--color-text-muted)" }}>PRODUCTS — DEVIATION FREQUENCY</p>
          <HorizontalBarChart rows={patterns.products.map((p) => ({ label: p.label, value: p.value }))} maxValue={maxProduct} primaryColor="#0d9488" />
          {patterns.products[0] && (
            <div className="an-note bad">
              <strong>Grey Area:</strong> {patterns.products[0].label} has the highest event count ({patterns.products[0].value}). Prioritise process review for this product line.
            </div>
          )}
        </div>
        <div className="an-card">
          <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "var(--color-text-muted)" }}>EQUIPMENT — ERROR &amp; BREAKDOWN FREQUENCY</p>
          <HorizontalBarChart rows={patterns.equipment.map((e) => ({ label: e.label, value: e.value }))} maxValue={maxEquipment} primaryColor="#0d9488" />
          {patterns.equipment[0] && (
            <div className="an-note warn">
              <strong>Grey Area:</strong> {patterns.equipment[0].label} leads with {patterns.equipment[0].value} events. Schedule preventive maintenance and calibration review.
            </div>
          )}
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
              <span className="an-badge" style={{ background: "var(--color-danger-bg)", color: "var(--color-danger-text)", flexShrink: 0 }}>{row.count} events</span>
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

const DATE_PRESET_OPTIONS = ["30", "90", "180", "365"];
function formatDatePreset(v: string): string {
  return v === "30" ? "Last 30 days" : v === "90" ? "Last 90 days" : v === "180" ? "Last 6 months" : "Last 12 months";
}

// Single filter bar for the whole page (per the user, 2026-08-03) — all 4
// real sections (Event, Root Cause, CAPA, Failure Pattern) share one query
// and re-fetch together rather than each keeping an independent filter
// state. Investigation Quality stays mock and keeps its own decorative
// pills (see InvestigationQualitySection) since it isn't wired to this.
function AnalyticsFilterBar({
  siteFilter,
  setSiteFilter,
  deptFilter,
  setDeptFilter,
  productFilter,
  setProductFilter,
  equipmentFilter,
  setEquipmentFilter,
  datePreset,
  setDatePreset,
  options,
}: {
  siteFilter: string;
  setSiteFilter: (v: string) => void;
  deptFilter: string;
  setDeptFilter: (v: string) => void;
  productFilter: string;
  setProductFilter: (v: string) => void;
  equipmentFilter: string;
  setEquipmentFilter: (v: string) => void;
  datePreset: string;
  setDatePreset: (v: string) => void;
  options: AnalyticsSummaryResponse["filter_options"];
}) {
  return (
    <div className="an-filters" style={{ marginBottom: 4 }}>
      <FilterSelect className="an-filter-pill" value={siteFilter} onChange={setSiteFilter} defaultLabel="All Sites" options={options.sites} />
      <FilterSelect className="an-filter-pill" value={deptFilter} onChange={setDeptFilter} defaultLabel="All Dept" options={options.departments} />
      <FilterSelect className="an-filter-pill" value={productFilter} onChange={setProductFilter} defaultLabel="All Product" options={options.products} />
      <FilterSelect className="an-filter-pill" value={equipmentFilter} onChange={setEquipmentFilter} defaultLabel="All Equipment" options={options.equipment} />
      <FilterSelect className="an-filter-pill" value={datePreset} onChange={setDatePreset} defaultLabel="All Time" options={DATE_PRESET_OPTIONS} formatOption={formatDatePreset} />
    </div>
  );
}

const EMPTY_FILTER_OPTIONS: AnalyticsSummaryResponse["filter_options"] = { sites: [], departments: [], products: [], equipment: [] };

export function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  const [siteFilter, setSiteFilter] = useState("");
  const [deptFilter, setDeptFilter] = useState("");
  const [productFilter, setProductFilter] = useState("");
  const [equipmentFilter, setEquipmentFilter] = useState("");
  const [datePreset, setDatePreset] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const startDateFrom = datePreset
      ? new Date(Date.now() - Number(datePreset) * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
      : undefined;
    getAnalyticsSummary({
      site: siteFilter || undefined,
      department: deptFilter || undefined,
      product: productFilter || undefined,
      equipment: equipmentFilter || undefined,
      startDateFrom,
    })
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? String(err.detail) : "Could not reach the database.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [retryKey, siteFilter, deptFilter, productFilter, equipmentFilter, datePreset]);

  // Only the full-page skeleton on first load — a filter-driven refetch
  // just dims the existing content in place (matches ActionCenterPage).
  if (loading && !summary) {
    return (
      <div className="an-page">
        <div className="an-card">
          <p style={{ margin: 0 }}>Loading analytics…</p>
        </div>
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="an-page">
        <div className="an-card">
          <p style={{ margin: 0, color: "var(--color-danger-text)" }}>{error ?? "No analytics data available."}</p>
          <button type="button" className="btn-outline" onClick={() => setRetryKey((k) => k + 1)}>Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="an-page" style={{ opacity: loading ? 0.6 : 1, transition: "opacity 150ms ease" }}>
      <AnalyticsFilterBar
        siteFilter={siteFilter}
        setSiteFilter={setSiteFilter}
        deptFilter={deptFilter}
        setDeptFilter={setDeptFilter}
        productFilter={productFilter}
        setProductFilter={setProductFilter}
        equipmentFilter={equipmentFilter}
        setEquipmentFilter={setEquipmentFilter}
        datePreset={datePreset}
        setDatePreset={setDatePreset}
        options={summary.filter_options ?? EMPTY_FILTER_OPTIONS}
      />
      <EventSection events={summary.events} />
      <RootCauseStatusSection status={summary.root_cause_status} categories={summary.root_cause_categories} />
      <CapaStatusSection capa={summary.capa} />
      <InvestigationQualitySection />
      <FailurePatternSection patterns={summary.failure_patterns} />
    </div>
  );
}