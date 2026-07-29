// Generic horizontal bar chart — supports a single value per row (with an
// optional per-row color) or a two-segment stacked row (e.g. "With RC" /
// "Probable RC"). Plain SVG, no charting library.

export interface HorizontalBarRow {
  label: string;
  value: number;
  secondaryValue?: number;
  color?: string;
}

const ROW_HEIGHT = 28;
const ROW_GAP = 8;
const LABEL_WIDTH = 110;
const CHART_WIDTH = 660;

export function HorizontalBarChart({
  rows,
  maxValue,
  primaryColor = "#22c55e",
  secondaryColor = "#f59e0b",
  legend,
}: {
  rows: HorizontalBarRow[];
  maxValue?: number;
  primaryColor?: string;
  secondaryColor?: string;
  legend?: { primary: string; secondary: string };
}) {
  const max = maxValue ?? Math.max(...rows.map((r) => r.value + (r.secondaryValue ?? 0)), 1);
  const totalHeight = rows.length * (ROW_HEIGHT + ROW_GAP);
  const scaleX = (v: number) => (v / max) * CHART_WIDTH;
  const tickCount = 4;
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => Math.round((max / tickCount) * i));

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${LABEL_WIDTH + CHART_WIDTH + 40} ${totalHeight + 24}`} style={{ overflow: "visible" }}>
        {ticks.map((tick) => {
          const x = LABEL_WIDTH + scaleX(tick);
          return (
            <g key={tick}>
              <line x1={x} x2={x} y1={0} y2={totalHeight} stroke="var(--color-card-border)" strokeDasharray="2 3" />
              <text x={x} y={totalHeight + 18} fontSize={11} textAnchor="middle" fill="var(--color-text-muted)">
                {tick}
              </text>
            </g>
          );
        })}
        {rows.map((row, i) => {
          const y = i * (ROW_HEIGHT + ROW_GAP);
          const primaryWidth = scaleX(row.value);
          const secondaryWidth = row.secondaryValue ? scaleX(row.secondaryValue) : 0;
          return (
            <g key={row.label}>
              <text x={LABEL_WIDTH - 8} y={y + ROW_HEIGHT / 2 + 4} fontSize={12} textAnchor="end" fill="var(--color-text)">
                {row.label}
              </text>
              {row.secondaryValue !== undefined ? (
                <>
                  <rect x={LABEL_WIDTH} y={y} width={secondaryWidth} height={ROW_HEIGHT} fill={secondaryColor} rx={2} />
                  <rect x={LABEL_WIDTH + secondaryWidth} y={y} width={primaryWidth} height={ROW_HEIGHT} fill={primaryColor} rx={2} />
                </>
              ) : (
                <rect x={LABEL_WIDTH} y={y} width={primaryWidth} height={ROW_HEIGHT} fill={row.color ?? primaryColor} rx={2} />
              )}
            </g>
          );
        })}
      </svg>
      {legend && (
        <div style={{ display: "flex", gap: 20, marginTop: 8, fontSize: 13, color: "var(--color-text-muted)" }}>
          <Legend swatch={primaryColor} label={legend.primary} />
          <Legend swatch={secondaryColor} label={legend.secondary} />
        </div>
      )}
    </div>
  );
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 10, height: 10, borderRadius: 2, background: swatch, display: "inline-block" }} />
      {label}
    </span>
  );
}
