import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import "./RecordModulePage.css";
import "./DataInterpretationPage.css";

// Data Interpretation (2026-09-22) — ported from Figma (file vFYyxUjVvQ0ICGysDga50H, node
// 3176:18940), step 5/8 of the investigation flow. Confirmed via a full DB schema search:
// no per-batch lab/analytical trend data exists anywhere in this app's database, so — same
// "static mock data, not wired to a backend" pattern as CxoDashboardPage — every number
// below is hardcoded from the Figma prototype. Shown for record 476050's product
// (APX-Lamotrigine) in the reference design; not tied to the viewed recordId's real data.

type Priority = "P1" | "P2" | "P3";

interface AnalysisListItem {
  priority: Priority;
  label: string;
}

const ANALYSIS_LIST: AnalysisListItem[] = [
  { priority: "P1", label: "Sifting time trend" },
  { priority: "P3", label: "Feeder speed vs Assay" },
  { priority: "P1", label: "Tablet weight trend" },
  { priority: "P1", label: "Capsule weight trend" },
  { priority: "P3", label: "Tamping position vs Assay" },
  { priority: "P1", label: "Locking length trend" },
  { priority: "P1", label: "Sifting time trend" },
  { priority: "P1", label: "Milling time trend" },
  { priority: "P1", label: "Drying time trend" },
  { priority: "P3", label: "LOD / moisture vs Assay" },
  { priority: "P1", label: "Ribbon thickness trend" },
  { priority: "P1", label: "Shell weight trend" },
  { priority: "P1", label: "Fill weight trend" },
  { priority: "P3", label: "Mixing time vs Assay" },
  { priority: "P3", label: "Bulk density vs Assay" },
  { priority: "P3", label: "Tapped density vs Assay" },
  { priority: "P3", label: "Batch-to-batch Assay variation" },
  { priority: "P2", label: "Operator-to-operator Assay variation" },
  { priority: "P2", label: "Machine-to-machine Assay variation" },
  { priority: "P3", label: "Hold time vs Assay" },
  { priority: "P3", label: "Granulation mixing time vs Assay" },
  { priority: "P3", label: "Bottom propeller speed vs Assay" },
  { priority: "P3", label: "REMI-stirrer speed vs Assay" },
];

const FAILURE_MODES = ["Assay", "Dissolution", "Related Substances", "Tablet Hardness", "Uniformity of Dosage Units", "Disintegration", "Water Content"];

interface TrendSeries {
  key: string;
  title: string;
  subtitle: string;
  status: "oos" | "in-spec";
  statusLabel: string;
  values: number[];
  max: number;
  // Index of the batch under investigation (Batch No. 7263940) — flagged consistently
  // across every panel in the reference design.
  highlightIndex: number;
  defaultMode: "bar" | "line";
}

const TREND_SERIES: TrendSeries[] = [
  {
    key: "assay",
    title: "Assay",
    subtitle: "Sifting time trend · min",
    status: "oos",
    statusLabel: "7 OOS",
    values: [24.66, 23.94, 18.64, 20.16, 19.13, 24.56, 20.29, 22.74],
    max: 30,
    highlightIndex: 3,
    defaultMode: "bar",
  },
  {
    key: "dissolution",
    title: "Dissolution",
    subtitle: "Dissolution (Q-30 min) trend · %",
    status: "oos",
    statusLabel: "1 OOS",
    values: [84.31, 90.85, 82.79, 88.33, 93.86, 82.69, 93.66, 83.85],
    max: 100,
    highlightIndex: 3,
    defaultMode: "line",
  },
  {
    key: "related-substances",
    title: "Related Substances",
    subtitle: "Total impurities trend · %",
    status: "in-spec",
    statusLabel: "In spec",
    values: [0.5, 0.52, 0.5, 0.44, 0.47, 0.52, 0.41, 0.48],
    max: 0.6,
    highlightIndex: 3,
    defaultMode: "bar",
  },
  {
    key: "tablet-hardness",
    title: "Tablet Hardness",
    subtitle: "Tablet hardness trend · kp",
    status: "in-spec",
    statusLabel: "In spec",
    values: [84.31, 90.85, 82.79, 88.33, 93.86, 82.69, 93.66, 83.85],
    max: 100,
    highlightIndex: 3,
    defaultMode: "line",
  },
  {
    key: "uniformity",
    title: "Uniformity of Dosage Units",
    subtitle: "Acceptance value (AV) trend · AV",
    status: "in-spec",
    statusLabel: "In spec",
    values: [6.66, 10.43, 8.19, 9.61, 10.09, 6.19, 8.87, 6.91],
    max: 12,
    highlightIndex: 3,
    defaultMode: "bar",
  },
  {
    key: "disintegration",
    title: "Disintegration",
    subtitle: "Disintegration time trend · min",
    status: "in-spec",
    statusLabel: "In spec",
    values: [8.42, 5, 5.77, 7.37, 7.66, 7.86, 5.54, 6.08],
    max: 10,
    highlightIndex: 3,
    defaultMode: "line",
  },
];

function ChevronDownIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.3-4.3" />
    </svg>
  );
}

function BarIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
      <path d="M6 20V10M12 20V4M18 20v-7" />
    </svg>
  );
}

function LineIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 17l6-6 4 4 8-9" />
    </svg>
  );
}

function FilterPill({ label }: { label: string }) {
  return (
    <button type="button" className="di-filter-pill">
      {label}
      <ChevronDownIcon />
    </button>
  );
}

// Plain SVG, no charting library — same hand-drawn convention as CxoDashboardPage's chart
// helpers. Renders as bars or a line+dots depending on `mode`; the highlighted batch (the
// one under investigation) always renders in the warning tone regardless of mode.
function TrendChart({ series, mode }: { series: TrendSeries; mode: "bar" | "line" }) {
  const w = 280;
  const h = 150;
  const n = series.values.length;
  const gap = 10;
  const barW = (w - gap * (n - 1)) / n;
  const xFor = (i: number) => (mode === "bar" ? i * (barW + gap) + barW / 2 : (i / (n - 1)) * w);
  const yFor = (v: number) => h - (v / series.max) * h;

  return (
    <svg viewBox={`-4 -18 ${w + 8} ${h + 30}`} width="100%" height={168}>
      {mode === "bar" ? (
        series.values.map((v, i) => {
          const barH = (v / series.max) * h;
          const highlighted = i === series.highlightIndex;
          return (
            <g key={i}>
              <rect
                x={i * (barW + gap)}
                y={h - barH}
                width={barW}
                height={Math.max(barH, 1)}
                rx={2}
                fill={highlighted ? "var(--color-warning-text)" : "var(--color-primary)"}
              />
              <text x={i * (barW + gap) + barW / 2} y={h - barH - 6} fontSize={10} fontWeight={600} fill="var(--color-text)" textAnchor="middle">
                {v}
              </text>
            </g>
          );
        })
      ) : (
        <>
          <path
            d={series.values.map((v, i) => `${i === 0 ? "M" : "L"}${xFor(i)},${yFor(v)}`).join(" ")}
            fill="none"
            stroke="var(--color-primary)"
            strokeWidth={2}
          />
          {series.values.map((v, i) => {
            const highlighted = i === series.highlightIndex;
            // Alternate the label above/below the point so consecutive close values don't overlap.
            const labelUp = yFor(v) > h / 2;
            return (
              <g key={i}>
                <circle cx={xFor(i)} cy={yFor(v)} r={highlighted ? 4 : 3} fill={highlighted ? "var(--color-warning-text)" : "var(--color-primary)"} />
                <text
                  x={xFor(i)}
                  y={labelUp ? yFor(v) - 8 : yFor(v) + 16}
                  fontSize={10}
                  fontWeight={600}
                  fill="var(--color-text)"
                  textAnchor="middle"
                >
                  {v}
                </text>
              </g>
            );
          })}
        </>
      )}
    </svg>
  );
}

function TrendChartCard({ series }: { series: TrendSeries }) {
  const [mode, setMode] = useState<"bar" | "line">(series.defaultMode);
  return (
    <div className="di-chart-card">
      <div className="di-chart-header">
        <div>
          <p className="di-chart-title">{series.title}</p>
          <p className="di-chart-subtitle">{series.subtitle}</p>
        </div>
        <span className={`di-chart-badge ${series.status}`}>{series.statusLabel}</span>
      </div>
      <div className="di-chart-body">
        <TrendChart series={series} mode={mode} />
      </div>
      <div className="di-chart-footer">
        <div className="di-chart-toggle">
          <button type="button" className={mode === "bar" ? "active" : ""} onClick={() => setMode("bar")} aria-label={`View ${series.title} as bars`} title="Bar view">
            <BarIcon />
          </button>
          <button type="button" className={mode === "line" ? "active" : ""} onClick={() => setMode("line")} aria-label={`View ${series.title} as a line`} title="Line view">
            <LineIcon />
          </button>
        </div>
        <span className="di-chart-caption">30 batches</span>
      </div>
    </div>
  );
}

export function DataInterpretationPage() {
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();
  const [activeFailureModes, setActiveFailureModes] = useState<Set<string>>(new Set());
  const [priority, setPriority] = useState<"All" | Priority>("All");
  const [search, setSearch] = useState("");
  const [activeAnalysis, setActiveAnalysis] = useState<string | null>(null);

  if (!recordId) return null;

  function toggleFailureMode(mode: string) {
    setActiveFailureModes((prev) => {
      const next = new Set(prev);
      if (next.has(mode)) next.delete(mode);
      else next.add(mode);
      return next;
    });
  }

  const filteredList = ANALYSIS_LIST.filter((item) => {
    if (priority !== "All" && item.priority !== priority) return false;
    if (search && !item.label.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="di-overview-row">
        <h2>Overview</h2>
        <div className="di-filter-row">
          <FilterPill label="Product Family" />
          <FilterPill label="SKUs" />
          <FilterPill label="Batch Number" />
          <FilterPill label="Batch Start & End date" />
        </div>
      </div>

      <div className="di-layout">
        <div className="di-sidebar">
          <div className="card">
            <p className="card-title" style={{ fontSize: "var(--font-size-md)" }}>
              Product under investigation
            </p>
            <p className="di-product-name">APX-Lamotrigine Caps USP 100mg — SGC</p>
            <div className="di-stat-row">
              <div className="di-stat-tile">
                <div className="di-stat-value">30</div>
                <div className="di-stat-label">Batches</div>
              </div>
              <div className="di-stat-tile">
                <div className="di-stat-value">44</div>
                <div className="di-stat-label">Analyses</div>
              </div>
            </div>
          </div>

          <div className="card">
            <p className="card-title" style={{ fontSize: "var(--font-size-md)" }}>
              Failure mode
            </p>
            <div className="di-pill-group">
              {FAILURE_MODES.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={`di-pill ${activeFailureModes.has(mode) ? "active" : ""}`}
                  onClick={() => toggleFailureMode(mode)}
                >
                  {mode}
                </button>
              ))}
            </div>

            <p className="card-title" style={{ fontSize: "var(--font-size-md)", marginTop: 4 }}>
              Priority
            </p>
            <div className="di-pill-group">
              {(["All", "P1", "P2", "P3"] as const).map((p) => (
                <button key={p} type="button" className={`di-pill ${priority === p ? "active" : ""}`} onClick={() => setPriority(p)}>
                  {p}
                </button>
              ))}
            </div>

            <div className="di-search-box">
              <SearchIcon />
              <input
                type="text"
                placeholder="Search analysis"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <div className="di-analysis-list">
              {filteredList.map((item, i) => (
                <button
                  key={`${item.label}-${i}`}
                  type="button"
                  className={`di-analysis-item ${activeAnalysis === `${item.label}-${i}` ? "active" : ""}`}
                  onClick={() => setActiveAnalysis(`${item.label}-${i}`)}
                >
                  <span className={`di-priority-badge ${item.priority.toLowerCase()}`}>{item.priority}</span>
                  {item.label}
                </button>
              ))}
              {filteredList.length === 0 && (
                <p style={{ margin: "8px 0", fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>No analyses match.</p>
              )}
            </div>
          </div>
        </div>

        <div className="di-chart-grid">
          {TREND_SERIES.map((series) => (
            <TrendChartCard key={series.key} series={series} />
          ))}
        </div>
      </div>

      <div className="footer-actions split">
        <button type="button" className="btn-outline" onClick={() => navigate(`/records/${recordId}/rci-plan`)}>
          Back to RCI Plan Creation
        </button>
        <button type="button" className="btn-primary" onClick={() => navigate(`/records/${recordId}/task-critique`)}>
          Next: Task Critique
        </button>
      </div>
    </div>
  );
}
