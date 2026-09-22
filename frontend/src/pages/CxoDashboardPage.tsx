import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { InfoTooltip } from "../components/InfoTooltip";
import "./ActionCenterPage.css";
import "./CxoDashboardPage.css";

// Every number below is STATIC mock data ported from the Figma prototype — no backend endpoint behind this page yet. CXO-role gated, same pattern as UserManagementPage's Admin gate.
// 2026-09-22 update: new Figma pass (file vFYyxUjVvQ0ICGysDga50H, nodes D1=3288:7031, D2=3297:810,
// D3=3297:2294, D4=3297:4188, D5=3600:36988) — adds the "Repeat Investigations" domain, richer
// panel sets per domain, and a "% split / Absolute" + expand control on every chart card. Per the
// user, those two controls are VISUAL ONLY for now (no backing "absolute" dataset exists, and
// nothing here is wired to a real endpoint yet) — see SplitToggle below.

type DomainKey = "quality" | "cycle" | "criticality" | "capa" | "repeat";
type DomainStatus = "below" | "on";

interface DomainMeta {
  key: DomainKey;
  label: string;
  value: string;
  caption: string;
  status: DomainStatus;
}

const DOMAINS: DomainMeta[] = [
  { key: "quality", label: "Investigation quality", value: "71%", caption: "definite root cause identified · target 85%", status: "below" },
  { key: "cycle", label: "Cycle time & backlog", value: "41 days", caption: "average closure time · target 20 Days", status: "below" },
  { key: "criticality", label: "Criticality & regulatory", value: "100%", caption: "High-risk escalated to Inv. Board · 1 FAR open", status: "on" },
  { key: "capa", label: "CAPA effectiveness & COPQ", value: "18%", caption: "repeat deviation rate · Target <5%", status: "below" },
  { key: "repeat", label: "Repeat Investigations", value: "45%", caption: "96 of 412 raised · 35 logged as new", status: "below" },
];

const TONE = {
  darkGreen: "#01543e",
  green: "#16a34a",
  teal: "#337263",
  brightTeal: "#009883",
  mint: "#86efac",
  orange: "#b45309",
  amber: "#f59e0b",
  red: "#dc2626",
  lightTeal: "#8fc4b6",
  grey: "#a8afb9",
  blue: "#1d4ed8",
};

// ── Small chart-building helpers (plain SVG, no charting library) ──────────────────────────────────────────────

function YAxis({
  max,
  steps = 4,
  width,
  height,
  labelOffset = 8,
}: {
  max: number;
  steps?: number;
  width: number;
  height: number;
  // How far left of x=0 the tick label sits — larger when the leftmost marker is wide (e.g. QualityDistributionChart's capsules), so the label clears it.
  labelOffset?: number;
}) {
  const ticks = Array.from({ length: steps + 1 }, (_, i) => Math.round((max / steps) * i));
  return (
    <>
      {ticks.map((t) => {
        const y = height - (t / max) * height;
        return (
          <g key={t}>
            <line x1={0} x2={width} y1={y} y2={y} stroke="var(--color-card-border)" strokeDasharray="2 3" />
            <text x={-labelOffset} y={y + 4} fontSize={10} fill="var(--color-text-muted)" textAnchor="end">
              {t}
            </text>
          </g>
        );
      })}
    </>
  );
}

// Visual-only "% split / Absolute" segmented control, shown on every chart card in the new design.
// No dataset backs "Absolute" yet — clicking it only changes which pill looks pressed.
function SplitToggle() {
  const [mode, setMode] = useState<"split" | "absolute">("split");
  return (
    <div className="cxo-split-toggle">
      <button type="button" className={mode === "split" ? "active" : ""} onClick={() => setMode("split")}>
        % split
      </button>
      <button type="button" className={mode === "absolute" ? "active" : ""} onClick={() => setMode("absolute")}>
        Absolute
      </button>
    </div>
  );
}

// Visual-only expand affordance — no modal/drill-down wired up yet.
function ExpandButton({ label }: { label: string }) {
  return (
    <button type="button" className="cxo-expand-btn" aria-label={`Expand ${label}`} title="Expand (not yet wired up)">
      ⤢
    </button>
  );
}

// "Investigation quality trend" grouped bar chart (D1, panel 1) — 3 series per month + delta badges between groups.
function GroupedTrendChart() {
  const months = ["Jun", "Jul", "Aug"];
  const series = [
    { label: "Definite root cause Identified", color: TONE.darkGreen, values: [38, 54, 28] },
    { label: "Accepted first time by SIT Lead", color: TONE.teal, values: [40, 40, 46] },
    { label: "Human error", color: TONE.mint, values: [48, 46, 60] },
  ];
  // Month-over-month change in "Definite root cause Identified" (the dark green series) — a delta, not a value of its own.
  const deltas = [
    { afterGroupIndex: 1, value: "+3%" },
    { afterGroupIndex: 2, value: "+3%" },
  ];
  const max = 80;
  const w = 560;
  const h = 220;
  const groupW = 120;
  const barW = 22;
  return (
    <svg viewBox={`-32 -10 ${w + 40} ${h + 50}`} width="100%" height={260}>
      <YAxis max={max} width={w} height={h} />
      {months.map((m, gi) => (
        <g key={m} transform={`translate(${gi * (groupW + 40)}, 0)`}>
          {series.map((s, si) => {
            const val = s.values[gi];
            const barH = (val / max) * h;
            return (
              <rect
                key={s.label}
                x={si * (barW + 6)}
                y={h - barH}
                width={barW}
                height={barH}
                fill={s.color}
                rx={2}
              />
            );
          })}
          <text x={groupW / 2 - 10} y={h + 20} fontSize={11} fontWeight={600} fill="var(--color-text)" textAnchor="middle">
            {m}
          </text>
        </g>
      ))}
      {deltas.map((d) => {
        // Fixed at the baseline, centered in the 40px gap between this group and the previous
        // one — independent of bar height, matching the reference design (not floating above
        // whichever bar happens to be tallest).
        const gapX = d.afterGroupIndex * (groupW + 40) - 40;
        return (
          <g key={d.afterGroupIndex} transform={`translate(${gapX}, ${h - 24})`}>
            <title>Change vs previous month — Definite root cause Identified</title>
            <rect width={40} height={20} rx={3} fill={TONE.blue} />
            <text x={20} y={14} fontSize={10.5} fontWeight={700} fill="#fff" textAnchor="middle">
              Δ {d.value}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// "Quality score distribution at pre-SIT gate" (D1, panel 2) — a colored capsule per score band joined by a dashed line.
function QualityDistributionChart() {
  const buckets = [
    { label: "<50", value: 16, tone: "low" },
    { label: "50-59", value: 26, tone: "low" },
    { label: "60-69", value: 50, tone: "medium" },
    { label: "70-79", value: 58, tone: "medium" },
    { label: "80-89", value: 80, tone: "medium" },
    { label: "90+", value: 100, tone: "high" },
  ] as const;
  const toneColor: Record<string, string> = { low: TONE.red, medium: TONE.amber, high: TONE.green };
  const max = 100;
  const w = 560;
  const h = 220;
  const step = w / (buckets.length - 1);
  const points = buckets.map((b, i) => ({ x: i * step, y: h - (b.value / max) * h, ...b }));
  return (
    <svg viewBox={`-70 -10 ${w + 78} ${h + 40}`} width="100%" height={260}>
      {/* Wider labelOffset — the leftmost capsule extends back to x=-24, so the default label position sat underneath it. */}
      <YAxis max={max} steps={5} width={w} height={h} labelOffset={36} />
      <path
        d={points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ")}
        fill="none"
        stroke="var(--color-card-border)"
        strokeDasharray="4 4"
      />
      {points.map((p) => (
        <rect
          key={p.label}
          x={p.x - 24}
          y={p.y - 11}
          width={48}
          height={22}
          rx={11}
          fill={toneColor[p.tone]}
        />
      ))}
      {points.map((p) => (
        <text key={`${p.label}-lbl`} x={p.x} y={h + 20} fontSize={11} fill="var(--color-text-muted)" textAnchor="middle">
          {p.label}
        </text>
      ))}
    </svg>
  );
}

// "Criticality parameter assessment completeness" — horizontal bar-with-dot list, reused by D1, D3.
function CompletenessBars({ data, showAxis }: { data: { label: string; value: number }[]; showAxis?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {data.map((row) => (
        <div key={row.label} style={{ display: "grid", gridTemplateColumns: "150px 1fr 40px", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>{row.label}</span>
          <svg viewBox="0 0 300 10" width="100%" height={10} preserveAspectRatio="none">
            <line x1={2} x2={298} y1={5} y2={5} stroke="var(--color-card-border)" strokeWidth={2} />
            <line x1={2} x2={2 + (row.value / 100) * 296} y1={5} y2={5} stroke={TONE.teal} strokeWidth={2} />
            <circle cx={2 + (row.value / 100) * 296} cy={5} r={4.5} fill={TONE.teal} />
          </svg>
          <span style={{ fontSize: "var(--font-size-sm)", fontWeight: 600, textAlign: "right" }}>{row.value}%</span>
        </div>
      ))}
      {showAxis && (
        <div style={{ display: "grid", gridTemplateColumns: "150px 1fr 40px", fontSize: 10, color: "var(--color-text-muted)" }}>
          <span />
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            {["0%", "25%", "50%", "75%", "100%"].map((t) => (
              <span key={t}>{t}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// "Investigation quality metrics by plant section" (D1, new) — stacked bar per section: Definite RC% (bottom) + RFT% (top).
function PlantSectionQualityChart() {
  const rows = [
    { label: "Granulation", rc: 57, rft: 88 },
    { label: "Compression", rc: 32, rft: 65 },
    { label: "Coating", rc: 52, rft: 78 },
    { label: "Packaging", rc: 32, rft: 65 },
    { label: "QC Lab", rc: 68, rft: 86 },
    { label: "Warehouse", rc: 40, rft: 80 },
  ];
  const max = 100;
  const w = 560;
  const h = 220;
  const groupW = 84;
  const barW = 40;
  return (
    <svg viewBox={`-32 -10 ${w + 40} ${h + 40}`} width="100%" height={260}>
      <YAxis max={max} steps={5} width={w} height={h} />
      {rows.map((r, i) => {
        const x = i * groupW + (groupW - barW) / 2;
        const rcH = (r.rc / max) * h;
        const rftH = (r.rft / max) * h;
        return (
          <g key={r.label}>
            <rect x={x} y={h - rftH} width={barW} height={rftH - rcH} fill={TONE.brightTeal} rx={2} />
            <rect x={x} y={h - rcH} width={barW} height={rcH} fill={TONE.darkGreen} rx={2} />
            <text x={x + barW / 2} y={h + 18} fontSize={10} fontWeight={600} fill="var(--color-text-muted)" textAnchor="middle">
              {r.label.toUpperCase()}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// "Investigator quality scorecard" (D1, new) — a donut gauge (pure CSS conic-gradient, no image asset) + 6 stat tiles.
function QualityScorecard() {
  const score = 76;
  const tiles: { label: string; value: string; suffix: string; dot: "green" | "orange" | "red" }[] = [
    { label: "Total Closed", value: "85%", suffix: "investigations", dot: "green" },
    { label: "Right First Time", value: "77%", suffix: "avg", dot: "green" },
    { label: "Definite RC", value: "71%", suffix: "avg", dot: "orange" },
    { label: "Avg Cycle", value: "40 D", suffix: "days avg", dot: "orange" },
    { label: "Top Investigator", value: "S. Iyer", suffix: "composite 91", dot: "green" },
    { label: "Bottom Investigator", value: "M. Khan", suffix: "composite 58", dot: "red" },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="cxo-gauge-wrap">
        <div
          className="cxo-gauge-ring"
          style={{
            background: `conic-gradient(${TONE.green} 0%, ${TONE.amber} ${score}%, var(--color-card-border) ${score}%, var(--color-card-border) 100%)`,
          }}
        >
          <div className="cxo-gauge-hole">
            <span className="cxo-gauge-score">{score}</span>
            <span className="cxo-gauge-label">TEAM COMPOSITE SCORE</span>
          </div>
        </div>
      </div>
      <div className="cxo-scorecard-tiles">
        {tiles.map((t) => (
          <div key={t.label} className="cxo-scorecard-tile">
            <div className="cxo-scorecard-tile-header">
              <span>{t.label}</span>
              <span className={`cxo-dot ${t.dot}`} />
            </div>
            <div className="cxo-scorecard-tile-value">
              <strong>{t.value}</strong>
              <span>{t.suffix}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// "Root cause classification — 6M" (D1, new) — horizontal overlaid bars per 6M category, one shade per month.
function RootCauseClassificationChart() {
  const rows = [
    { label: "Man", jun: 43, jul: 50, aug: 62 },
    { label: "Method", jun: 21, jul: 25, aug: 30 },
    { label: "Materiel", jun: 27, jul: 32, aug: 38 },
    { label: "Machine", jun: 35, jul: 42, aug: 50 },
    { label: "Measurement", jun: 40, jul: 48, aug: 58 },
    { label: "Mother Nature", jun: 10, jul: 12, aug: 14 },
  ];
  const max = 100;
  const w = 560;
  const rowH = 30;
  const barH = 14;
  const h = rows.length * rowH;
  return (
    <>
      <svg viewBox={`-110 -10 ${w + 140} ${h + 30}`} width="100%" height={280}>
        {[0, 25, 50, 75, 100].map((t) => (
          <g key={t}>
            <line x1={(t / max) * w} x2={(t / max) * w} y1={-4} y2={h + 4} stroke="var(--color-card-border)" strokeDasharray="2 3" />
            <text x={(t / max) * w} y={h + 18} fontSize={10} fill="var(--color-text-muted)" textAnchor="middle">
              {t}%
            </text>
          </g>
        ))}
        {rows.map((r, i) => {
          const y = i * rowH;
          return (
            <g key={r.label}>
              <text x={-10} y={y + barH / 2 + 4} fontSize={10} fontWeight={600} fill="var(--color-text-muted)" textAnchor="end">
                {r.label.toUpperCase()}
              </text>
              <rect x={0} y={y} width={(r.aug / max) * w} height={barH} fill={TONE.mint} rx={2} />
              <rect x={0} y={y} width={(r.jul / max) * w} height={barH} fill={TONE.brightTeal} rx={2} />
              <rect x={0} y={y} width={(r.jun / max) * w} height={barH} fill={TONE.darkGreen} rx={2} />
            </g>
          );
        })}
      </svg>
      <div className="cxo-legend-row">
        <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.darkGreen } as React.CSSProperties}>
          Jun
        </span>
        <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.brightTeal } as React.CSSProperties}>
          Jul
        </span>
        <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.mint } as React.CSSProperties}>
          Aug
        </span>
      </div>
    </>
  );
}

// "Stage wise cycle time vs SLA" (D2, panel 1) — horizontal dual-bar list.
function StageCycleTimeBars() {
  const rows = [
    { label: "Problem Statement", actual: 8, sla: 10 },
    { label: "Evidence Collection", actual: 9, sla: 11 },
    { label: "Interview Questionnaire", actual: 24, sla: 18 },
    { label: "RCI Plan Creation", actual: 22, sla: 16 },
    { label: "Task Critique", actual: 11, sla: 14 },
    { label: "RC & CAPA Critique", actual: 9, sla: 13 },
    { label: "RCI Report", actual: 7, sla: 15 },
  ];
  const max = 26;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {rows.map((r) => (
        <div key={r.label} style={{ display: "grid", gridTemplateColumns: "150px 1fr", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>{r.label}</span>
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <div style={{ height: 8, borderRadius: 2, width: `${(r.actual / max) * 100}%`, background: TONE.darkGreen }} />
            <div style={{ height: 8, borderRadius: 2, width: `${(r.sla / max) * 100}%`, background: TONE.lightTeal }} />
          </div>
        </div>
      ))}
    </div>
  );
}

// "Aging analysis — 142 open investigations" (D2, new) — stacked columns by escalation level, Critical/Major/Minor.
function AgingAnalysisChart() {
  const rows = [
    { label: "L1", critical: 2, major: 4, minor: 6 },
    { label: "L2", critical: 2, major: 4, minor: 6 },
    { label: "L3", critical: 4, major: 10, minor: 14 },
    { label: "L4", critical: 3, major: 7, minor: 12 },
    { label: "L5", critical: 0, major: 0, minor: 3 },
  ];
  const max = 60;
  const w = 500;
  const h = 200;
  const barW = 60;
  const gap = 40;
  return (
    <>
      <svg viewBox={`-32 -10 ${w + 40} ${h + 40}`} width="100%" height={240}>
        <YAxis max={max} steps={4} width={w} height={h} />
        {rows.map((r, i) => {
          const x = i * (barW + gap);
          const redH = (r.critical / max) * h;
          const orangeH = (r.major / max) * h;
          const greenH = (r.minor / max) * h;
          return (
            <g key={r.label}>
              <rect x={x} y={h - redH} width={barW} height={redH} fill={TONE.red} />
              <rect x={x} y={h - redH - orangeH} width={barW} height={orangeH} fill={TONE.amber} />
              <rect x={x} y={h - redH - orangeH - greenH} width={barW} height={greenH} fill={TONE.darkGreen} />
              <text x={x + barW / 2} y={h + 20} fontSize={11} fill="var(--color-text-muted)" textAnchor="middle">
                {r.label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="cxo-legend-row">
        <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.red } as React.CSSProperties}>
          Critical
        </span>
        <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.amber } as React.CSSProperties}>
          Major
        </span>
        <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.darkGreen } as React.CSSProperties}>
          Minor
        </span>
      </div>
    </>
  );
}

// "Inflow, closure and open backlog" (D2, panel 3) — stacked bar + dashed trend line.
function InflowClosureChart() {
  const months = ["Jun", "Jul", "Aug"];
  const bottom = [20, 18, 22];
  const top = [22, 20, 28];
  const trend = [42, 38, 46];
  const max = 80;
  const w = 500;
  const h = 200;
  const barW = 70;
  const gap = 90;
  const step = w / (months.length - 1);
  return (
    <svg viewBox={`-32 -10 ${w + 40} ${h + 40}`} width="100%" height={240}>
      <YAxis max={max} steps={4} width={w} height={h} />
      {months.map((m, i) => {
        const x = i * (barW + gap - barW);
        const bottomH = (bottom[i] / max) * h;
        const topH = (top[i] / max) * h;
        return (
          <g key={m}>
            <rect x={x} y={h - bottomH} width={barW} height={bottomH} fill={TONE.lightTeal} />
            <rect x={x} y={h - bottomH - topH} width={barW} height={topH} fill={TONE.teal} />
            <text x={x + barW / 2} y={h + 20} fontSize={11} fill="var(--color-text-muted)" textAnchor="middle">
              {m}
            </text>
          </g>
        );
      })}
      <path
        d={trend.map((v, i) => `${i === 0 ? "M" : "L"}${i * step + barW / 2},${h - (v / max) * h}`).join(" ")}
        fill="none"
        stroke={TONE.red}
        strokeDasharray="5 4"
        strokeWidth={2}
      />
    </svg>
  );
}

// "Closure velocity vs plan" (D2, panel 4) — grouped bar pairs.
function ClosureVelocityChart() {
  const months = ["Jun", "Jul", "Aug"];
  const actual = [430, 460, 530];
  const plan = [390, 430, 510];
  const max = 600;
  const w = 500;
  const h = 200;
  const groupW = 100;
  const barW = 34;
  return (
    <svg viewBox={`-32 -10 ${w + 40} ${h + 40}`} width="100%" height={240}>
      <YAxis max={max} steps={4} width={w} height={h} />
      {months.map((m, i) => {
        const x = i * (groupW + 40);
        const actualH = (actual[i] / max) * h;
        const planH = (plan[i] / max) * h;
        return (
          <g key={m}>
            <rect x={x} y={h - actualH} width={barW} height={actualH} fill={TONE.teal} />
            <rect x={x + barW + 6} y={h - planH} width={barW} height={planH} fill={TONE.lightTeal} />
            <text x={x + barW} y={h + 20} fontSize={11} fill="var(--color-text-muted)" textAnchor="middle">
              {m}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// "Investigator workload analysis" (D2, new) — scatter, x=open cases assigned, y=average age of cases.
function InvestigatorWorkloadChart() {
  const points: { x: number; y: number; tone: "balanced" | "watch" | "overloaded" }[] = [
    { x: 5, y: 33, tone: "watch" },
    { x: 6, y: 27, tone: "balanced" },
    { x: 6, y: 44, tone: "overloaded" },
    { x: 7, y: 20, tone: "overloaded" },
    { x: 7, y: 34, tone: "balanced" },
    { x: 7, y: 48, tone: "watch" },
    { x: 8, y: 36, tone: "overloaded" },
    { x: 8, y: 38, tone: "watch" },
    { x: 9, y: 10, tone: "overloaded" },
    { x: 9, y: 15, tone: "watch" },
    { x: 9, y: 52, tone: "balanced" },
  ];
  const toneColor: Record<string, string> = { balanced: TONE.darkGreen, watch: TONE.amber, overloaded: TONE.red };
  const maxX = 18;
  const maxY = 60;
  const w = 900;
  const h = 200;
  return (
    <>
      <svg viewBox={`-40 -10 ${w + 60} ${h + 60}`} width="100%" height={260}>
        <YAxis max={maxY} steps={4} width={w} height={h} />
        {points.map((p, i) => (
          <circle key={i} cx={(p.x / maxX) * w} cy={h - (p.y / maxY) * h} r={6} fill={toneColor[p.tone]} />
        ))}
        {[5, 6, 7, 8, 9, 12, 13, 15, 18].map((t) => (
          <text key={t} x={(t / maxX) * w} y={h + 20} fontSize={10} fill="var(--color-text-muted)" textAnchor="middle">
            {t}
          </text>
        ))}
        <text x={w / 2} y={h + 46} fontSize={11} fill="var(--color-text-muted)" textAnchor="middle">
          Open cases assigned
        </text>
      </svg>
      <div className="cxo-legend-row">
        <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.darkGreen } as React.CSSProperties}>
          Balanced
        </span>
        <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.amber } as React.CSSProperties}>
          Watch
        </span>
        <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.red } as React.CSSProperties}>
          Overloaded
        </span>
      </div>
    </>
  );
}

// "Event trend by classification" (D3) and "Recurrence and effectiveness trend" (D4) — same stacked-bar shape, different series/scale, so one shared component.
function QuarterlyStackedChart({
  max,
  seriesLabels,
  data,
}: {
  max: number;
  seriesLabels: [string, string, string];
  data: { quarter: string; a: number; b: number; c: number }[];
}) {
  const w = 560;
  const h = 220;
  const barW = 44;
  const gap = 26;
  return (
    <>
      <svg viewBox={`-32 -10 ${w + 40} ${h + 40}`} width="100%" height={260}>
        <YAxis max={max} width={w} height={h} />
        {data.map((d, i) => {
          const x = i * (barW + gap);
          const aH = (d.a / max) * h;
          const bH = (d.b / max) * h;
          const cH = (d.c / max) * h;
          return (
            <g key={d.quarter}>
              <rect x={x} y={h - aH} width={barW} height={aH} fill={TONE.red} />
              <rect x={x} y={h - aH - bH} width={barW} height={bH} fill={TONE.amber} />
              <rect x={x} y={h - aH - bH - cH} width={barW} height={cH} fill={TONE.darkGreen} />
              <text x={x + barW / 2} y={h + 18} fontSize={9.5} fill="var(--color-text-muted)" textAnchor="middle">
                {d.quarter}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="cxo-legend-row">
        {seriesLabels.map((l, i) => (
          <span
            key={l}
            className="cxo-legend-swatch dot"
            style={{ "--swatch-color": [TONE.red, TONE.amber, TONE.darkGreen][i] } as React.CSSProperties}
          >
            {l}
          </span>
        ))}
      </div>
    </>
  );
}

// "Time to action — interim vs final" (D3, Detailed analysis anchor A) — grouped bar, dual axis (hours left / days right).
function TimeToActionChart() {
  const rows = [
    { label: "Critical", interim: 6, final: 31 },
    { label: "Major", interim: 14, final: 26 },
    { label: "Minor", interim: 38, final: 19 },
  ];
  const maxInterim = 40;
  const maxFinal = 60;
  const w = 380;
  const h = 220;
  const groupW = 100;
  const barW = 34;
  return (
    <svg viewBox={`-32 -10 ${w + 60} ${h + 40}`} width="100%" height={260}>
      <YAxis max={maxInterim} width={w} height={h} />
      {rows.map((r, i) => {
        const x = i * (groupW + 30);
        const interimH = (r.interim / maxInterim) * h;
        const finalH = (r.final / maxFinal) * h;
        return (
          <g key={r.label}>
            <rect x={x} y={h - interimH} width={barW} height={interimH} fill={TONE.teal} />
            <rect x={x + barW + 6} y={h - finalH} width={barW} height={finalH} fill={TONE.darkGreen} />
            <text x={x + barW} y={h + 18} fontSize={11} fill="var(--color-text-muted)" textAnchor="middle">
              {r.label}
            </text>
          </g>
        );
      })}
      {[0, 15, 30, 45, 60].map((t) => (
        <text key={t} x={w + 12} y={h - (t / maxFinal) * h + 4} fontSize={10} fill="var(--color-text-muted)" textAnchor="start">
          {t}
        </text>
      ))}
    </svg>
  );
}

// "Pareto of major failure modes" (D4, panel 2) — bars + cumulative % line, dual axis.
function ParetoChart() {
  const bars = [
    { label: "SOP Error", value: 22, tail: false },
    { label: "", value: 18, tail: false },
    { label: "Equipment", value: 15, tail: false },
    { label: "", value: 13, tail: false },
    { label: "Analytical", value: 11, tail: false },
    { label: "", value: 9, tail: true },
    { label: "Other", value: 10, tail: true },
  ];
  const max = 40;
  const w = 560;
  const h = 220;
  const barW = 56;
  const gap = 20;
  let running = 0;
  const total = bars.reduce((s, b) => s + b.value, 0);
  const cumulative = bars.map((b) => {
    running += b.value;
    return running / total;
  });
  return (
    <svg viewBox={`-32 -10 ${w + 60} ${h + 40}`} width="100%" height={260}>
      <YAxis max={max} width={w} height={h} />
      {bars.map((b, i) => {
        const x = i * (barW + gap);
        const barH = (b.value / max) * h;
        return (
          <g key={i}>
            <rect x={x} y={h - barH} width={barW} height={barH} fill={b.tail ? TONE.grey : TONE.teal} />
            {b.label && (
              <text x={x + barW / 2} y={h + 18} fontSize={10.5} fill="var(--color-text-muted)" textAnchor="middle">
                {b.label}
              </text>
            )}
          </g>
        );
      })}
      <path
        d={cumulative.map((c, i) => `${i === 0 ? "M" : "L"}${i * (barW + gap) + barW / 2},${h - c * h}`).join(" ")}
        fill="none"
        stroke="#101828"
        strokeWidth={1.5}
      />
      {cumulative.map((c, i) => (
        <circle key={i} cx={i * (barW + gap) + barW / 2} cy={h - c * h} r={3} fill="#101828" />
      ))}
      {[0, 25, 50, 75, 100].map((t) => (
        <text key={t} x={w + 12} y={h - (t / 100) * h + 4} fontSize={10} fill="var(--color-text-muted)" textAnchor="start">
          {t}%
        </text>
      ))}
    </svg>
  );
}

// "From investigations raised to repeats logged as new" (D5, new) — horizontal funnel/waterfall bars.
function RepeatFunnelChart() {
  const rows = [
    { label: "Investigations Raised", value: 412, color: TONE.darkGreen },
    { label: "Single Occurance", value: 316, color: TONE.grey },
    { label: "Repeat Investigation", value: 96, color: TONE.darkGreen },
    { label: "Flagged as Repeat", value: 61, color: TONE.grey },
    { label: "Logged as New", value: 35, color: TONE.amber },
  ];
  const max = 600;
  const w = 560;
  const rowH = 44;
  const barH = 26;
  const h = rows.length * rowH;
  return (
    <>
      <svg viewBox={`-160 -10 ${w + 168} ${h + 30}`} width="100%" height={h + 60}>
        {[0, 150, 300, 450, 600].map((t) => (
          <g key={t}>
            <line x1={(t / max) * w} x2={(t / max) * w} y1={-4} y2={h + 4} stroke="var(--color-card-border)" strokeDasharray="2 3" />
            <text x={(t / max) * w} y={h + 18} fontSize={10} fill="var(--color-text-muted)" textAnchor="middle">
              {t}
            </text>
          </g>
        ))}
        {rows.map((r, i) => {
          const y = i * rowH + (rowH - barH) / 2;
          return (
            <g key={r.label}>
              <text x={-10} y={y + barH / 2 + 4} fontSize={10} fontWeight={600} fill="var(--color-text-muted)" textAnchor="end">
                {r.label.toUpperCase()}
              </text>
              <rect x={0} y={y} width={(r.value / max) * w} height={barH} fill={r.color} rx={2} />
            </g>
          );
        })}
      </svg>
      <p style={{ margin: "8px 0 0", fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
        412 investigations raised → 96 repeats → 61 flagged by the investigator, 35 logged as new.
      </p>
    </>
  );
}

// "Repeat linkage by month" (D5, new) — stacked bar + dashed trend line.
function RepeatLinkageByMonthChart() {
  const months = ["Jun", "Jul", "Aug"];
  const loggedAsNew = [20, 12, 18];
  const flaggedAsRepeat = [20, 23, 24];
  const trend = [40, 35, 42];
  const max = 80;
  const w = 500;
  const h = 200;
  const barW = 70;
  const step = w / (months.length - 1);
  return (
    <>
      <svg viewBox={`-32 -10 ${w + 40} ${h + 40}`} width="100%" height={240}>
        <YAxis max={max} steps={4} width={w} height={h} />
        {months.map((m, i) => {
          const x = i * ((w - barW) / (months.length - 1));
          const bottomH = (loggedAsNew[i] / max) * h;
          const topH = (flaggedAsRepeat[i] / max) * h;
          return (
            <g key={m}>
              <rect x={x} y={h - bottomH} width={barW} height={bottomH} fill={TONE.lightTeal} />
              <rect x={x} y={h - bottomH - topH} width={barW} height={topH} fill={TONE.darkGreen} />
              <text x={x + barW / 2} y={h + 20} fontSize={11} fill="var(--color-text-muted)" textAnchor="middle">
                {m}
              </text>
            </g>
          );
        })}
        <path
          d={trend.map((v, i) => `${i === 0 ? "M" : "L"}${i * step + barW / 2},${h - (v / max) * h}`).join(" ")}
          fill="none"
          stroke={TONE.red}
          strokeDasharray="5 4"
          strokeWidth={2}
        />
      </svg>
      <div className="cxo-legend-row">
        <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.lightTeal } as React.CSSProperties}>
          Logged as new
        </span>
        <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.darkGreen } as React.CSSProperties}>
          Flagged as repeat by investigator
        </span>
      </div>
    </>
  );
}

// "Repeats by product family" (D5, new) — horizontal two-segment bars, 0-100%.
function RepeatsByProductFamilyChart() {
  const rows = [
    { label: "Amlodipine ER", flagged: 40, repeat: 28 },
    { label: "Metformin XR", flagged: 38, repeat: 24 },
    { label: "Atorvastatin FC", flagged: 55, repeat: 40 },
    { label: "Levetiracetam", flagged: 50, repeat: 38 },
    { label: "Sertraline", flagged: 42, repeat: 30 },
    { label: "Pantoprazole", flagged: 34, repeat: 24 },
    { label: "Other 8 families", flagged: 28, repeat: 20 },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {rows.map((r) => {
        const total = r.flagged + r.repeat;
        return (
          <div key={r.label} style={{ display: "grid", gridTemplateColumns: "140px 1fr", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>{r.label.toUpperCase()}</span>
            <div style={{ display: "flex", height: 14, borderRadius: 3, overflow: "hidden" }}>
              <div style={{ width: `${r.repeat}%`, background: TONE.darkGreen }} />
              <div style={{ width: `${r.flagged}%`, background: TONE.brightTeal }} />
              <div style={{ width: `${100 - total}%`, background: "var(--color-card-border)" }} />
            </div>
          </div>
        );
      })}
      <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", fontSize: 10, color: "var(--color-text-muted)" }}>
        <span />
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          {["0%", "25%", "50%", "75%", "100%"].map((t) => (
            <span key={t}>{t}</span>
          ))}
        </div>
      </div>
      <div className="cxo-legend-row">
        <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.darkGreen } as React.CSSProperties}>
          Repeat investigations
        </span>
        <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.brightTeal } as React.CSSProperties}>
          Flagged as repeat
        </span>
      </div>
    </div>
  );
}

// ── Risk concentration heatmap + Regulatory register — plain data tables, values read verbatim off the Figma screens. ────────────────

const RISK_CONCENTRATION: { area: string; critical: number | null; major: number | null; minor: number | null }[] = [
  { area: "Granulation", critical: 3, major: 14, minor: 9 },
  { area: "Compression", critical: 2, major: 11, minor: 16 },
  { area: "Coating", critical: 1, major: 7, minor: 12 },
  { area: "Packing L4", critical: 4, major: 17, minor: 13 },
  { area: "Packing L6", critical: 1, major: 9, minor: 10 },
  { area: "QC wet lab", critical: 2, major: 12, minor: 8 },
  { area: "Warehouse", critical: null, major: 4, minor: 7 },
];

// Tone per cell is read off the Figma design, not derived from the count — the same number can carry a different tone in different cells.
const RISK_TONE: Record<string, "low" | "moderate" | "high" | "critical"> = {
  "Granulation:critical": "high",
  "Granulation:major": "critical",
  "Granulation:minor": "low",
  "Compression:critical": "moderate",
  "Compression:major": "high",
  "Compression:minor": "moderate",
  "Coating:critical": "low",
  "Coating:major": "moderate",
  "Coating:minor": "moderate",
  "Packing L4:critical": "critical",
  "Packing L4:major": "critical",
  "Packing L4:minor": "moderate",
  "Packing L6:critical": "low",
  "Packing L6:major": "high",
  "Packing L6:minor": "moderate",
  "QC wet lab:critical": "moderate",
  "QC wet lab:major": "critical",
  "QC wet lab:minor": "moderate",
  "Warehouse:major": "moderate",
  "Warehouse:minor": "moderate",
};

const REGULATORY_REGISTER: {
  ref: string;
  type: string;
  typeClass: string;
  parent: string;
  agency: string;
  clock: string;
  urgent: boolean;
  status: string;
  batches: number;
  owner: string;
  ownerInitials: string;
}[] = [
  {
    ref: "FAR-26-003",
    type: "FAR (US)",
    typeClass: "far",
    parent: "OOS-26-0092",
    agency: "US FDA · 3 working days",
    clock: "1d 6h left",
    urgent: true,
    status: "Draft with RA",
    batches: 2,
    owner: "S. Iyer",
    ownerInitials: "SI",
  },
  {
    ref: "FA-26-001",
    type: "Field alert (EU)",
    typeClass: "field-alert",
    parent: "DEV-26-0311",
    agency: "EMA · QP notified",
    clock: "Closed on day 2",
    urgent: false,
    status: "Submitted",
    batches: 1,
    owner: "R. Menon",
    ownerInitials: "RM",
  },
  {
    ref: "REC-25-002",
    type: "Recall Cl. II",
    typeClass: "recall",
    parent: "DEV-25-0904",
    agency: "India CDSCO",
    clock: "Complete",
    urgent: false,
    status: "Effectiveness check done",
    batches: 6,
    owner: "A. Rao",
    ownerInitials: "AR",
  },
  {
    ref: "PEN-26-004",
    type: "Assessment",
    typeClass: "assessment",
    parent: "DEV-26-0418",
    agency: "Reportability under review",
    clock: "Decision due 8 Aug",
    urgent: false,
    status: "Open",
    batches: 1,
    owner: "Inv. Board",
    ownerInitials: "IB",
  },
];

function RiskConcentrationTable() {
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="cxo-heatmap-table">
        <thead>
          <tr>
            <th></th>
            <th>Critical</th>
            <th>Major</th>
            <th>Minor</th>
          </tr>
        </thead>
        <tbody>
          {RISK_CONCENTRATION.map((row) => (
            <tr key={row.area}>
              <td style={{ color: "var(--color-text-muted)" }}>{row.area}</td>
              {(["critical", "major", "minor"] as const).map((col) => {
                const v = row[col];
                if (v === null) return <td key={col}>–</td>;
                const tone = RISK_TONE[`${row.area}:${col}`] ?? "low";
                return (
                  <td key={col}>
                    <span className={`cxo-heatmap-cell ${tone}`}>{v}</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="cxo-legend-row">
        <span className="cxo-legend-swatch" style={{ "--swatch-color": "var(--color-success-text)" } as React.CSSProperties}>
          Low
        </span>
        <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.teal } as React.CSSProperties}>
          Moderate
        </span>
        <span className="cxo-legend-swatch" style={{ "--swatch-color": "var(--color-warning-text)" } as React.CSSProperties}>
          High
        </span>
        <span className="cxo-legend-swatch" style={{ "--swatch-color": "var(--color-danger-text)" } as React.CSSProperties}>
          Critical
        </span>
      </div>
    </div>
  );
}

function RegulatoryRegisterTable() {
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="cxo-register-table">
        <thead>
          <tr>
            <th>Ref</th>
            <th>Type</th>
            <th>Parent investigation</th>
            <th>Agency / market</th>
            <th>Statutory clock</th>
            <th>Status</th>
            <th>Batches</th>
            <th>Owner</th>
          </tr>
        </thead>
        <tbody>
          {REGULATORY_REGISTER.map((row) => (
            <tr key={row.ref}>
              <td>{row.ref}</td>
              <td>
                <span className={`cxo-register-type-badge ${row.typeClass}`}>{row.type}</span>
              </td>
              <td style={{ color: "var(--color-info-text)" }}>{row.parent}</td>
              <td style={{ color: "var(--color-text-muted)" }}>{row.agency}</td>
              <td className={row.urgent ? "cxo-register-clock urgent" : undefined}>{row.clock}</td>
              <td>{row.status}</td>
              <td>{row.batches}</td>
              <td>
                <div className="cxo-owner-cell">
                  <span className="cxo-owner-avatar">{row.ownerInitials}</span>
                  {row.owner}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ObservationBox / DetailedAnalysisBox render identically (same green-bordered style in the Figma
// design) — a pair shown side by side wherever both apply.
function ObservationRow({ observation, detailedAnalysis }: { observation: string; detailedAnalysis: string }) {
  return (
    <div className="cxo-chart-grid" style={{ marginTop: 16 }}>
      <div className="cxo-observation-box">
        <strong>Observation:</strong> {observation}
      </div>
      <div className="cxo-observation-box">
        <strong>Detailed Analysis:</strong> {detailedAnalysis}
      </div>
    </div>
  );
}

function ViewSitDashboardFooter() {
  const navigate = useNavigate();
  return (
    <button type="button" className="cxo-footer-link" onClick={() => navigate("/")}>
      <span className="cxo-footer-link-icon" aria-hidden>
        ☰
      </span>
      <span>
        <strong>View SIT Dashboard</strong>
        <span className="cxo-footer-link-caption">142 open records</span>
      </span>
      <span className="cxo-footer-link-arrow" aria-hidden>
        →
      </span>
    </button>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="cxo-chart-card">
      <div className="cxo-chart-title-row">
        <div className="cxo-chart-title-left">
          <h3>{title}</h3>
          <ExpandButton label={title} />
          <InfoTooltip label={`What this shows: ${title}`}>
            <p style={{ margin: 0, fontSize: "var(--font-size-sm)" }}>Static reference chart, ported from the Figma prototype.</p>
          </InfoTooltip>
        </div>
        <SplitToggle />
      </div>
      {children}
    </div>
  );
}

export function CxoDashboardPage() {
  const { roles } = useAuth();
  const navigate = useNavigate();
  const isCxo = roles.includes("CXO");
  const [activeDomain, setActiveDomain] = useState<DomainKey>("quality");
  const [repeatView, setRepeatView] = useState<"families" | "batches">("families");

  if (!isCxo) {
    return (
      <div className="ac-page-bg">
        <div className="ac-page">
          <div className="ac-card">
            <p style={{ margin: 0 }}>This page is only available to CXO users.</p>
            <button type="button" className="btn-outline" style={{ marginTop: 12 }} onClick={() => navigate("/")}>
              Back to Action Center
            </button>
          </div>
        </div>
      </div>
    );
  }

  const active = DOMAINS.find((d) => d.key === activeDomain)!;

  return (
    <div className="ac-page-bg">
      <div className="ac-page">
        <div className="cxo-header-row">
          <div>
            <h1>CXO Dashboard</h1>
            <p>KRSG Plant</p>
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <span className="cxo-filter-pill">KRSG ▾</span>
            <span className="cxo-filter-pill">T-3 Months ▾</span>
          </div>
        </div>

        <div className="ac-card" style={{ marginTop: 16 }}>
          <h2 className="cxo-section-title">Performance By Domain</h2>

          <div className="cxo-domain-row">
            {DOMAINS.map((d) => (
              <button
                key={d.key}
                type="button"
                className={`cxo-domain-card ${d.key === activeDomain ? `active ${d.status}` : ""}`}
                onClick={() => setActiveDomain(d.key)}
              >
                <div className="cxo-domain-label">{d.label}</div>
                <div className={`cxo-domain-value ${d.status}`}>{d.value}</div>
                <div className="cxo-domain-caption">{d.caption}</div>
                <span className={`cxo-domain-badge ${d.status}`}>{d.status === "below" ? "BELOW TARGET" : "ON TARGET"}</span>
              </button>
            ))}
          </div>

          <div className={`cxo-detail-panel ${active.status}`}>
            {activeDomain === "quality" && (
              <>
                <div className="cxo-chart-grid">
                  <ChartCard title="Investigation quality metrics by plant section">
                    <PlantSectionQualityChart />
                    <div className="cxo-legend-row">
                      <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.darkGreen } as React.CSSProperties}>
                        Definite RC%
                      </span>
                      <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.brightTeal } as React.CSSProperties}>
                        RFT%
                      </span>
                    </div>
                  </ChartCard>
                  <ChartCard title="Investigator quality scorecard">
                    <QualityScorecard />
                  </ChartCard>
                </div>
                <div className="cxo-chart-grid" style={{ marginTop: 16 }}>
                  <ChartCard title="Investigation quality trend">
                    <GroupedTrendChart />
                    <div className="cxo-legend-row">
                      <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.darkGreen } as React.CSSProperties}>
                        Definite root cause Identified
                      </span>
                      <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.teal } as React.CSSProperties}>
                        Accepted first time by SIT Lead
                      </span>
                      <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.mint } as React.CSSProperties}>
                        Human error
                      </span>
                    </div>
                  </ChartCard>
                  <ChartCard title="Quality score distribution at pre-SIT gate">
                    <QualityDistributionChart />
                    <div className="cxo-legend-row">
                      <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.red } as React.CSSProperties}>
                        Low (&lt;60)
                      </span>
                      <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.amber } as React.CSSProperties}>
                        Medium (60-89)
                      </span>
                      <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.green } as React.CSSProperties}>
                        High (90+)
                      </span>
                    </div>
                  </ChartCard>
                </div>
                <div className="cxo-chart-grid" style={{ marginTop: 16 }}>
                  <ChartCard title="Event trend by classification">
                    <QuarterlyStackedChart
                      max={70}
                      seriesLabels={["Critical", "Major", "Minor"]}
                      data={[
                        { quarter: "Q3-24", a: 8, b: 15, c: 22 },
                        { quarter: "Q4-24", a: 5, b: 13, c: 20 },
                        { quarter: "Q1-25", a: 10, b: 20, c: 28 },
                        { quarter: "Q2-25", a: 8, b: 15, c: 24 },
                        { quarter: "Q3-25", a: 3, b: 5, c: 8 },
                        { quarter: "Q4-25", a: 6, b: 14, c: 22 },
                        { quarter: "Q1-26", a: 9, b: 18, c: 30 },
                        { quarter: "Q2-26", a: 2, b: 5, c: 10 },
                      ]}
                    />
                  </ChartCard>
                  <ChartCard title="Criticality parameter assessment completeness">
                    <CompletenessBars
                      data={[
                        { label: "Patient safety", value: 92 },
                        { label: "Product quality", value: 85 },
                        { label: "GMP / regulatory", value: 88 },
                        { label: "Other batches affected", value: 76 },
                        { label: "Validated state", value: 72 },
                        { label: "Repeat linkage", value: 68 },
                      ]}
                    />
                  </ChartCard>
                </div>

                <ObservationRow
                  observation='Low scores are concentrated in two investigators, indicating a coaching requirement rather than a process gap.'
                  detailedAnalysis="Root Cause Classification, Investigator Scorecard, Risk Concentration By Area"
                />

                <div className="cxo-chart-grid" style={{ marginTop: 16 }}>
                  <ChartCard title="Root cause classification — 6M">
                    <RootCauseClassificationChart />
                  </ChartCard>
                  <ChartCard title="Risk concentration — area × severity">
                    <RiskConcentrationTable />
                  </ChartCard>
                </div>
              </>
            )}

            {activeDomain === "cycle" && (
              <>
                <div className="cxo-chart-grid">
                  <ChartCard title="Stage wise cycle time vs SLA">
                    <StageCycleTimeBars />
                    <div className="cxo-legend-row">
                      <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.darkGreen } as React.CSSProperties}>
                        Actual Days
                      </span>
                      <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.lightTeal } as React.CSSProperties}>
                        SLA Allowance
                      </span>
                    </div>
                  </ChartCard>
                  <ChartCard title="Aging analysis — 142 open investigations">
                    <AgingAnalysisChart />
                  </ChartCard>
                </div>
                <div className="cxo-chart-grid" style={{ marginTop: 16 }}>
                  <ChartCard title="Inflow, closure and open backlog">
                    <InflowClosureChart />
                  </ChartCard>
                  <ChartCard title="Closure velocity vs plan">
                    <ClosureVelocityChart />
                  </ChartCard>
                </div>
                <div style={{ marginTop: 16 }}>
                  <ChartCard title="Investigator workload analysis">
                    <InvestigatorWorkloadChart />
                  </ChartCard>
                </div>
                <div style={{ marginTop: 16 }}>
                  <ViewSitDashboardFooter />
                </div>
              </>
            )}

            {activeDomain === "criticality" && (
              <>
                <div className="cxo-chart-grid">
                  <ChartCard title="Event trend by classification, 8 quarters">
                    <QuarterlyStackedChart
                      max={70}
                      seriesLabels={["Critical", "Major", "Minor"]}
                      data={[
                        { quarter: "Q3-24", a: 8, b: 15, c: 22 },
                        { quarter: "Q4-24", a: 5, b: 13, c: 20 },
                        { quarter: "Q1-25", a: 10, b: 20, c: 28 },
                        { quarter: "Q2-25", a: 8, b: 15, c: 24 },
                        { quarter: "Q3-25", a: 3, b: 5, c: 8 },
                        { quarter: "Q4-25", a: 6, b: 14, c: 22 },
                        { quarter: "Q1-26", a: 9, b: 18, c: 30 },
                        { quarter: "Q2-26", a: 2, b: 5, c: 10 },
                      ]}
                    />
                  </ChartCard>
                  <ChartCard title="Criticality parameter assessment completeness">
                    <CompletenessBars
                      showAxis
                      data={[
                        { label: "Patient Safety", value: 98 },
                        { label: "Product Quality", value: 95 },
                        { label: "GMP/Regulatory", value: 97 },
                        { label: "Other batches affected", value: 94 },
                        { label: "Validated State", value: 90 },
                        { label: "Repeat Linkage", value: 88 },
                      ]}
                    />
                  </ChartCard>
                </div>

                <ObservationRow
                  observation='"Other batches or products affected" is documented in 76% of investigations. This parameter determines reportability. One FAR reporting window closes within 1 day 6 hours.'
                  detailedAnalysis="Time to action, risk concentration by area, regulatory register"
                />

                <div className="cxo-chart-grid" style={{ marginTop: 16 }}>
                  <ChartCard title="Time to action — interim vs final">
                    <TimeToActionChart />
                    <div className="cxo-legend-row">
                      <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.teal } as React.CSSProperties}>
                        Interim action (hours)
                      </span>
                      <span className="cxo-legend-swatch dot" style={{ "--swatch-color": TONE.darkGreen } as React.CSSProperties}>
                        Final action (days)
                      </span>
                    </div>
                  </ChartCard>
                  <ChartCard title="Risk concentration — area × severity">
                    <RiskConcentrationTable />
                  </ChartCard>
                </div>

                <div className="cxo-chart-card" style={{ marginTop: 16 }}>
                  <div className="cxo-chart-title-row">
                    <div className="cxo-chart-title-left">
                      <h3>Regulatory and market-action register</h3>
                      <ExpandButton label="Regulatory and market-action register" />
                    </div>
                    <SplitToggle />
                  </div>
                  <RegulatoryRegisterTable />
                </div>

                <div style={{ marginTop: 16 }}>
                  <ViewSitDashboardFooter />
                </div>
              </>
            )}

            {activeDomain === "capa" && (
              <>
                <div className="cxo-chart-grid">
                  <ChartCard title="Recurrence and effectiveness trend, 8 quarters">
                    <QuarterlyStackedChart
                      max={8}
                      seriesLabels={["Repeat Deviations", "CAPA Effectiveness", "Batch Rejections"]}
                      data={[
                        { quarter: "Q3-24", a: 1, b: 2, c: 2 },
                        { quarter: "Q4-24", a: 1, b: 2, c: 2 },
                        { quarter: "Q1-25", a: 1, b: 2, c: 3 },
                        { quarter: "Q2-25", a: 1, b: 2, c: 2 },
                        { quarter: "Q3-25", a: 0.5, b: 1, c: 1 },
                        { quarter: "Q4-25", a: 1, b: 2, c: 2.5 },
                        { quarter: "Q1-26", a: 1, b: 2, c: 3 },
                        { quarter: "Q2-26", a: 0.5, b: 0.5, c: 1 },
                      ]}
                    />
                  </ChartCard>
                  <ChartCard title="Pareto of major failure modes">
                    <ParetoChart />
                  </ChartCard>
                </div>

                <ObservationRow
                  observation="Five failure modes account for 73% of major events, led by SOP error. Repeat deviations sit at 18% against a target of under 5%."
                  detailedAnalysis="Recurrence Trend, Pareto Of Major Failure Modes"
                />
              </>
            )}

            {activeDomain === "repeat" && (
              <>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                  <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                    Viewing repeat recurrence by{" "}
                    <strong style={{ color: "var(--color-text)" }}>
                      {repeatView === "families" ? "product families affected" : "batches affected"}
                    </strong>
                  </span>
                  <div className="cxo-split-toggle">
                    <button type="button" className={repeatView === "families" ? "active" : ""} onClick={() => setRepeatView("families")}>
                      Product families affected
                    </button>
                    <button type="button" className={repeatView === "batches" ? "active" : ""} onClick={() => setRepeatView("batches")}>
                      Batches affected
                    </button>
                  </div>
                </div>

                <div className="cxo-scorecard-tiles" style={{ marginBottom: 16 }}>
                  <div className="cxo-scorecard-tile">
                    <div className="cxo-scorecard-tile-header">
                      <span>Families Affected</span>
                      <span className="cxo-dot orange" />
                    </div>
                    <div className="cxo-scorecard-tile-value">
                      <strong>14</strong>
                      <span>of 38 marketed</span>
                    </div>
                  </div>
                  <div className="cxo-scorecard-tile">
                    <div className="cxo-scorecard-tile-header">
                      <span>Repeat Rate</span>
                      <span className="cxo-dot orange" />
                    </div>
                    <div className="cxo-scorecard-tile-value">
                      <strong>23%</strong>
                      <span>of investigations</span>
                    </div>
                  </div>
                  <div className="cxo-scorecard-tile">
                    <div className="cxo-scorecard-tile-header">
                      <span>Flagged By Investigator</span>
                      <span className="cxo-dot green" />
                    </div>
                    <div className="cxo-scorecard-tile-value">
                      <strong>61</strong>
                      <span>64% of repeats</span>
                    </div>
                  </div>
                  <div className="cxo-scorecard-tile">
                    <div className="cxo-scorecard-tile-header">
                      <span>Logged As New</span>
                      <span className="cxo-dot red" />
                    </div>
                    <div className="cxo-scorecard-tile-value">
                      <strong>35</strong>
                      <span>36% missed linkage</span>
                    </div>
                  </div>
                </div>

                <div style={{ marginBottom: 16 }}>
                  <ChartCard title="From investigations raised to repeats logged as new">
                    <RepeatFunnelChart />
                  </ChartCard>
                </div>

                <div className="cxo-chart-grid">
                  <ChartCard title="Repeat linkage by month">
                    <RepeatLinkageByMonthChart />
                  </ChartCard>
                  <ChartCard title="Repeats by product family">
                    <RepeatsByProductFamilyChart />
                  </ChartCard>
                </div>

                <ObservationRow
                  observation="96 of 412 investigations are repeats, and 35 of them were logged as brand-new events instead of being linked to the earlier case — the recurrence is real but under-reported."
                  detailedAnalysis="Repeat Investigation Waterfall, Linkage Trend, Concentration By Product Family And Batch"
                />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
