// Multi-series line chart. Plain SVG, no charting library.
export interface LineSeries {
  name: string;
  color: string;
  values: number[];
}

const CHART_HEIGHT = 180;
const CHART_WIDTH = 640;

export function LineChart({
  categories,
  series,
  yMin,
  yMax,
}: {
  categories: string[];
  series: LineSeries[];
  yMin?: number;
  yMax?: number;
}) {
  const allValues = series.flatMap((s) => s.values);
  const min = yMin ?? Math.min(...allValues);
  const max = yMax ?? Math.max(...allValues);
  const range = max - min || 1;
  const stepX = CHART_WIDTH / (categories.length - 1 || 1);
  const scaleX = (i: number) => i * stepX;
  const scaleY = (v: number) => CHART_HEIGHT - ((v - min) / range) * CHART_HEIGHT;

  const yTicks = 4;
  const ticks = Array.from({ length: yTicks + 1 }, (_, i) => min + (range / yTicks) * i);

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${CHART_WIDTH + 50} ${CHART_HEIGHT + 30}`} style={{ overflow: "visible" }}>
        {ticks.map((tick) => {
          const y = scaleY(tick) + 10;
          return (
            <g key={tick}>
              <line x1={35} x2={CHART_WIDTH + 35} y1={y} y2={y} stroke="var(--color-card-border)" strokeDasharray="2 3" />
              <text x={28} y={y + 4} textAnchor="end" fontSize={11} fill="var(--color-text-muted)">
                {Math.round(tick)}
              </text>
            </g>
          );
        })}
        {categories.map((c, i) => (
          <text key={c} x={35 + scaleX(i)} y={CHART_HEIGHT + 26} textAnchor="middle" fontSize={11} fill="var(--color-text-muted)">
            {c}
          </text>
        ))}
        {series.map((s) => {
          const points = s.values.map((v, i) => `${35 + scaleX(i)},${scaleY(v) + 10}`).join(" ");
          return (
            <g key={s.name}>
              <polyline points={points} fill="none" stroke={s.color} strokeWidth={2} />
              {s.values.map((v, i) => (
                <circle key={i} cx={35 + scaleX(i)} cy={scaleY(v) + 10} r={3} fill="var(--color-surface)" stroke={s.color} strokeWidth={2}>
                  <title>{`${s.name} — ${categories[i]}: ${v}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
      </svg>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8, fontSize: 12, color: "var(--color-text-muted)" }}>
        {series.map((s) => (
          <span key={s.name} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 10, height: 10, borderRadius: "50%", background: s.color, display: "inline-block" }} />
            {s.name}
          </span>
        ))}
      </div>
    </div>
  );
}
