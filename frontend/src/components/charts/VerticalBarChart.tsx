// Simple single-series vertical bar chart. Plain SVG, no charting library.
export interface VerticalBarDatum {
  label: string;
  value: number;
}

const CHART_HEIGHT = 160;
const BAR_WIDTH = 40;
const SLOT_WIDTH = 90;

export function VerticalBarChart({ data, color = "#00786f", yLabel }: { data: VerticalBarDatum[]; color?: string; yLabel?: string }) {
  const maxValue = Math.max(...data.map((d) => d.value), 1);
  const niceMax = Math.ceil(maxValue / 4) * 4 || 4;
  const yTicks = [0, niceMax / 4, niceMax / 2, (niceMax * 3) / 4, niceMax];
  const scaleY = (v: number) => (v / niceMax) * CHART_HEIGHT;
  const plotWidth = data.length * SLOT_WIDTH;

  return (
    <svg width="100%" viewBox={`0 0 ${plotWidth + 50} ${CHART_HEIGHT + 40}`} style={{ overflow: "visible" }}>
      {yTicks.map((tick) => {
        const y = CHART_HEIGHT - scaleY(tick) + 10;
        return (
          <g key={tick}>
            <line x1={40} x2={plotWidth + 40} y1={y} y2={y} stroke="var(--color-card-border)" strokeDasharray="2 3" />
            <text x={30} y={y + 4} textAnchor="end" fontSize="var(--font-size-xs)" fill="var(--color-text-muted)">
              {Math.round(tick)}
            </text>
          </g>
        );
      })}
      {yLabel && (
        <text x={5} y={0} fontSize="var(--font-size-xs)" fill="var(--color-text-muted)">
          {yLabel}
        </text>
      )}
      {data.map((d, i) => {
        const x = 48 + i * SLOT_WIDTH + (SLOT_WIDTH - BAR_WIDTH) / 2;
        const barHeight = scaleY(d.value);
        const y = CHART_HEIGHT + 10 - barHeight;
        return (
          <g key={d.label}>
            <rect x={x} y={y} width={BAR_WIDTH} height={barHeight} fill={color} rx={3}>
              <title>{`${d.label}: ${d.value}`}</title>
            </rect>
            <text x={x + BAR_WIDTH / 2} y={CHART_HEIGHT + 28} textAnchor="middle" fontSize="var(--font-size-sm)" fill="var(--color-text-muted)">
              {d.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
