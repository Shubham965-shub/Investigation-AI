import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { InfoTooltip } from "../components/InfoTooltip";
import "./ActionCenterPage.css";
import "./CxoDashboardPage.css";

// Every number below is STATIC mock data ported from the Figma prototype — no backend endpoint behind this page yet. CXO-role gated, same pattern as UserManagementPage's Admin gate.

type DomainKey = "quality" | "cycle" | "criticality" | "capa";
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
];

const TONE = {
  darkGreen: "#01543e",
  green: "#16a34a",
  teal: "#337263",
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
        const rootCauseBarH = (series[0].values[d.afterGroupIndex] / max) * h;
        const groupX = d.afterGroupIndex * (groupW + 40);
        return (
          <g key={d.afterGroupIndex} transform={`translate(${groupX - 6}, ${h - rootCauseBarH - 28})`}>
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
    { label: "<50", value: 22, tone: "low" },
    { label: "50-59", value: 35, tone: "low" },
    { label: "60-69", value: 68, tone: "medium" },
    { label: "70-79", value: 78, tone: "medium" },
    { label: "80-89", value: 108, tone: "medium" },
    { label: "90+", value: 135, tone: "high" },
  ] as const;
  const toneColor: Record<string, string> = { low: TONE.red, medium: TONE.amber, high: TONE.green };
  const max = 150;
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

// Second "Investigation quality trend" (D1, panel 3) — stacked area/band chart, same 3 categories as the grouped bar above.
function StackedAreaTrendChart() {
  const months = ["Jun", "Jul", "Aug"];
  const green = [45, 40, 45];
  const orange = [40, 35, 40];
  const red = [45, 28, 45];
  const max = 180;
  const w = 560;
  const h = 220;
  const step = w / (months.length - 1);
  const bandPath = (bottom: number[], top: number[]) => {
    const topPts = top.map((v, i) => `${i === 0 ? "M" : "L"}${i * step},${h - (v / max) * h}`).join(" ");
    const bottomPts = bottom
      .map((v, i) => `L${(months.length - 1 - i) * step},${h - (v / max) * h}`)
      .join(" ");
    return `${topPts} ${bottomPts} Z`;
  };
  const redTop = red;
  const orangeTop = red.map((v, i) => v + orange[i]);
  const greenTop = orangeTop.map((v, i) => v + green[i]);
  return (
    <svg viewBox={`-32 -10 ${w + 40} ${h + 40}`} width="100%" height={260}>
      <YAxis max={max} width={w} height={h} />
      <path d={bandPath(new Array(months.length).fill(0), redTop)} fill={TONE.red} opacity={0.55} />
      <path d={bandPath(redTop, orangeTop)} fill={TONE.amber} opacity={0.55} />
      <path d={bandPath(orangeTop, greenTop)} fill={TONE.green} opacity={0.45} />
      {months.map((m, i) => (
        <text key={m} x={i * step} y={h + 20} fontSize={11} fill="var(--color-text-muted)" textAnchor="middle">
          {m}
        </text>
      ))}
    </svg>
  );
}

// "Criticality parameter assessment completeness" — horizontal bar-with-dot list, reused by both D1 (no axis) and D3 (0-100% axis).
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

// "Stage wise cycle time vs SLA" (D2, panel 2) — stacked columns L1-L5.
function StageCycleTimeColumns() {
  const rows = [
    { label: "L1", red: 5, orange: 7, green: 5 },
    { label: "L2", red: 4, orange: 6, green: 5 },
    { label: "L3", red: 6, orange: 8, green: 6 },
    { label: "L4", red: 5, orange: 6, green: 5 },
    { label: "L5", red: 0, orange: 0, green: 3 },
  ];
  const max = 30;
  const w = 500;
  const h = 200;
  const barW = 60;
  const gap = 40;
  return (
    <svg viewBox={`-32 -10 ${w + 40} ${h + 40}`} width="100%" height={240}>
      <YAxis max={max} steps={4} width={w} height={h} />
      {rows.map((r, i) => {
        const x = i * (barW + gap);
        const redH = (r.red / max) * h;
        const orangeH = (r.orange / max) * h;
        const greenH = (r.green / max) * h;
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

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="cxo-chart-card">
      <div className="cxo-chart-title-row">
        <h3>{title}</h3>
        <InfoTooltip label={`What this shows: ${title}`}>
          <p style={{ margin: 0, fontSize: "var(--font-size-sm)" }}>Static reference chart, ported from the Figma prototype.</p>
        </InfoTooltip>
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
  const [showAnchorSection, setShowAnchorSection] = useState<"time" | "risk" | "register" | null>(null);

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
                onClick={() => {
                  setActiveDomain(d.key);
                  setShowAnchorSection(null);
                }}
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
                <div className="cxo-chart-grid">
                  <ChartCard title="Investigation quality trend">
                    <StackedAreaTrendChart />
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
                  <ChartCard title="Stage wise cycle time vs SLA">
                    <StageCycleTimeColumns />
                    <div className="cxo-legend-row">
                      <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.darkGreen } as React.CSSProperties}>
                        Actual Days
                      </span>
                      <span className="cxo-legend-swatch" style={{ "--swatch-color": TONE.amber } as React.CSSProperties}>
                        SLA Allowance
                      </span>
                    </div>
                  </ChartCard>
                </div>
                <div className="cxo-chart-grid">
                  <ChartCard title="Inflow, closure and open backlog">
                    <InflowClosureChart />
                  </ChartCard>
                  <ChartCard title="Closure velocity vs plan">
                    <ClosureVelocityChart />
                  </ChartCard>
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

                <div className="cxo-observation-box">
                  <strong>Observation:</strong> "Other batches or products affected" is documented in 76% of investigations. This
                  parameter determines reportability. One FAR reporting window closes within 1 day 6 hours.
                </div>

                <div className="cxo-anchor-row">
                  <span className="label">Detailed analysis</span>
                  <button type="button" className="cxo-anchor-link" onClick={() => setShowAnchorSection("time")}>
                    Time to Action
                  </button>
                  <span className="cxo-anchor-sep">,</span>
                  <button type="button" className="cxo-anchor-link" onClick={() => setShowAnchorSection("risk")}>
                    Risk Concentration By Area
                  </button>
                  <span className="cxo-anchor-sep">,</span>
                  <button type="button" className="cxo-anchor-link" onClick={() => setShowAnchorSection("register")}>
                    Regulatory Register
                  </button>
                </div>

                {showAnchorSection === "time" && (
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
                )}
                {showAnchorSection === "risk" && (
                  <div className="cxo-chart-card" style={{ marginTop: 16 }}>
                    <div className="cxo-chart-title-row">
                      <h3>Risk concentration - area × severity</h3>
                    </div>
                    <RiskConcentrationTable />
                  </div>
                )}
                {showAnchorSection === "register" && (
                  <div className="cxo-chart-card" style={{ marginTop: 16 }}>
                    <div className="cxo-chart-title-row">
                      <h3>Regulatory and market-action register</h3>
                    </div>
                    <RegulatoryRegisterTable />
                  </div>
                )}
              </>
            )}

            {activeDomain === "capa" && (
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
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
