// Stacked bar chart for "Status Of Open Investigations". Plain SVG, no
// charting library. Each bar is clipped to a single rounded-top-only shape
// so the stacked segments read as one continuous column with flush color
// transitions — only the very top of the whole bar is rounded, matching
// the approved Figma design. Colors are likewise fixed by that design.
export interface StatusChartDatum {
  label: string;
  onTrack: number;
  atRisk: number;
  delayed: number;
}

const COLORS = {
  onTrack: "#3b82f6",
  atRisk: "#f59e0b",
  delayed: "#dc2626",
};

const CHART_HEIGHT = 200;
const BAR_WIDTH = 66;
const SLOT_WIDTH = 176;
const CORNER_RADIUS = 4;

function roundedTopRectPath(x: number, y: number, width: number, height: number, radius: number): string {
  const r = Math.min(radius, height, width / 2);
  return [
    `M ${x} ${y + height}`,
    `L ${x} ${y + r}`,
    `A ${r} ${r} 0 0 1 ${x + r} ${y}`,
    `L ${x + width - r} ${y}`,
    `A ${r} ${r} 0 0 1 ${x + width} ${y + r}`,
    `L ${x + width} ${y + height}`,
    "Z",
  ].join(" ");
}

// Picks a small set of evenly-spaced, round-number tick values (e.g.
// 0/100/200/300/400) instead of one per integer — the latter is fine for
// tiny totals but unreadable once real counts (e.g. 382) are plotted.
function niceTicks(maxValue: number, targetCount = 5): number[] {
  if (maxValue <= 0) return [0, 1, 2, 3, 4];
  const rawStep = maxValue / targetCount;
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const residual = rawStep / magnitude;
  let step: number;
  if (residual > 5) step = 10 * magnitude;
  else if (residual > 2) step = 5 * magnitude;
  else if (residual > 1) step = 2 * magnitude;
  else step = magnitude;
  const niceMax = Math.ceil(maxValue / step) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= niceMax; v += step) ticks.push(v);
  return ticks;
}

export function StatusChart({ data }: { data: StatusChartDatum[] }) {
  const rawMax = Math.max(4, ...data.map((d) => d.onTrack + d.atRisk + d.delayed));
  const yTicks = niceTicks(rawMax);
  const maxTotal = yTicks[yTicks.length - 1];
  const plotWidth = data.length * SLOT_WIDTH;
  const scaleY = (value: number) => (value / maxTotal) * CHART_HEIGHT;

  return (
    <div>
      <svg
        role="img"
        aria-label="Status of open investigations by stage"
        width="100%"
        viewBox={`0 0 ${plotWidth + 48} ${CHART_HEIGHT + 40}`}
        style={{ overflow: "visible" }}
      >
        {yTicks.map((tick) => {
          const y = CHART_HEIGHT - scaleY(tick) + 10;
          return (
            <g key={tick}>
              <line x1={40} x2={plotWidth + 40} y1={y} y2={y} stroke="var(--color-card-border)" strokeDasharray="2 3" />
              <text x={30} y={y + 4} textAnchor="end" fontSize={12} fill="var(--color-text-muted)">
                {tick}
              </text>
            </g>
          );
        })}

        {data.map((d, i) => {
          const x = 48 + i * SLOT_WIDTH + (SLOT_WIDTH - BAR_WIDTH) / 2;
          const baseline = CHART_HEIGHT + 10;
          const total = d.onTrack + d.atRisk + d.delayed;
          const totalHeight = scaleY(total);
          const barTop = baseline - totalHeight;
          const clipId = `bar-clip-${i}`;

          // Bottom to top: Delayed, At Risk, On Track — "On track" (blue) is
          // always the topmost segment in the approved design.
          const segments = [
            { key: "delayed", value: d.delayed, color: COLORS.delayed },
            { key: "atRisk", value: d.atRisk, color: COLORS.atRisk },
            { key: "onTrack", value: d.onTrack, color: COLORS.onTrack },
          ];

          let cursor = baseline;
          return (
            <g key={d.label}>
              {total > 0 && (
                <clipPath id={clipId}>
                  <path d={roundedTopRectPath(x, barTop, BAR_WIDTH, totalHeight, CORNER_RADIUS)} />
                </clipPath>
              )}
              <g clipPath={total > 0 ? `url(#${clipId})` : undefined}>
                {segments.map((seg) => {
                  if (seg.value <= 0) return null;
                  const height = scaleY(seg.value);
                  const y = cursor - height;
                  cursor = y;
                  return (
                    <rect key={seg.key} x={x} y={y} width={BAR_WIDTH} height={height} fill={seg.color}>
                      <title>{`${d.label} — ${seg.key}: ${seg.value}`}</title>
                    </rect>
                  );
                })}
              </g>
              <text x={x + BAR_WIDTH / 2} y={CHART_HEIGHT + 28} textAnchor="middle" fontSize={12} fill="var(--color-text-muted)">
                {d.label}
              </text>
            </g>
          );
        })}
      </svg>

      <div style={{ display: "flex", gap: 20, marginTop: 12, fontSize: 13, color: "var(--color-text-muted)" }}>
        <Legend swatch={COLORS.onTrack} label="On track" />
        <Legend swatch={COLORS.atRisk} label="At Risk" />
        <Legend swatch={COLORS.delayed} label="Delayed" />
      </div>
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
