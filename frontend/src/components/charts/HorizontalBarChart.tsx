// Generic horizontal bar chart — single value per row, or a two-segment stacked row. wrapLabel() measures against an offscreen canvas since SVG <text> doesn't wrap on its own.

export interface HorizontalBarRow {
  label: string;
  value: number;
  secondaryValue?: number;
  color?: string;
}

const BAR_HEIGHT = 28;
const ROW_GAP = 8;
const LABEL_WIDTH = 130;
const CHART_WIDTH = 660;
const LABEL_FONT_SIZE = 12;
const LABEL_LINE_HEIGHT = 14;
// Generic sans-serif, not the app's --font-body — canvas can't resolve CSS custom properties; a slightly wider font just makes wrapping conservative.
const MEASURE_FONT = `${LABEL_FONT_SIZE}px Arial, Helvetica, sans-serif`;

let measureCanvasCtx: CanvasRenderingContext2D | null = null;
function measureTextWidth(text: string): number {
  if (!measureCanvasCtx) {
    measureCanvasCtx = document.createElement("canvas").getContext("2d");
  }
  if (!measureCanvasCtx) return text.length * LABEL_FONT_SIZE * 0.6; // no canvas support — rough fallback
  measureCanvasCtx.font = MEASURE_FONT;
  return measureCanvasCtx.measureText(text).width;
}

// Greedy word-wrap; a single word wider than maxWidth is left as its own overflowing line rather than broken mid-word.
function wrapLabel(label: string, maxWidth: number): string[] {
  const words = label.split(/\s+/).filter(Boolean);
  if (words.length === 0) return [label];
  const lines: string[] = [];
  let current = words[0];
  for (const word of words.slice(1)) {
    const candidate = `${current} ${word}`;
    if (measureTextWidth(candidate) <= maxWidth) {
      current = candidate;
    } else {
      lines.push(current);
      current = word;
    }
  }
  lines.push(current);
  return lines;
}

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
  const scaleX = (v: number) => (v / max) * CHART_WIDTH;
  const tickCount = 4;
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => Math.round((max / tickCount) * i));

  const wrappedLabels = rows.map((row) => wrapLabel(row.label, LABEL_WIDTH - 8));
  const rowHeights = wrappedLabels.map((lines) => Math.max(BAR_HEIGHT, lines.length * LABEL_LINE_HEIGHT));
  const rowTops: number[] = [];
  let cursor = 0;
  for (const h of rowHeights) {
    rowTops.push(cursor);
    cursor += h + ROW_GAP;
  }
  const totalHeight = cursor - ROW_GAP;

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${LABEL_WIDTH + CHART_WIDTH + 40} ${totalHeight + 24}`} style={{ overflow: "visible" }}>
        {ticks.map((tick) => {
          const x = LABEL_WIDTH + scaleX(tick);
          return (
            <g key={tick}>
              <line x1={x} x2={x} y1={0} y2={totalHeight} stroke="var(--color-card-border)" strokeDasharray="2 3" />
              <text x={x} y={totalHeight + 18} fontSize="var(--font-size-xs)" textAnchor="middle" fill="var(--color-text-muted)">
                {tick}
              </text>
            </g>
          );
        })}
        {rows.map((row, i) => {
          const y = rowTops[i];
          const rowHeight = rowHeights[i];
          const lines = wrappedLabels[i];
          const primaryWidth = scaleX(row.value);
          const secondaryWidth = row.secondaryValue ? scaleX(row.secondaryValue) : 0;
          const barY = y + (rowHeight - BAR_HEIGHT) / 2;
          const textBlockHeight = lines.length * LABEL_LINE_HEIGHT;
          const firstLineY = y + rowHeight / 2 - textBlockHeight / 2 + LABEL_LINE_HEIGHT * 0.78;
          return (
            <g key={row.label}>
              <text x={LABEL_WIDTH - 8} fontSize="var(--font-size-sm)" textAnchor="end" fill="var(--color-text)">
                {lines.map((line, li) => (
                  <tspan key={li} x={LABEL_WIDTH - 8} y={firstLineY + li * LABEL_LINE_HEIGHT}>
                    {line}
                  </tspan>
                ))}
              </text>
              {row.secondaryValue !== undefined ? (
                <>
                  <rect x={LABEL_WIDTH} y={barY} width={secondaryWidth} height={BAR_HEIGHT} fill={secondaryColor} rx={2} />
                  <rect x={LABEL_WIDTH + secondaryWidth} y={barY} width={primaryWidth} height={BAR_HEIGHT} fill={primaryColor} rx={2} />
                </>
              ) : (
                <rect x={LABEL_WIDTH} y={barY} width={primaryWidth} height={BAR_HEIGHT} fill={row.color ?? primaryColor} rx={2} />
              )}
            </g>
          );
        })}
      </svg>
      {legend && (
        <div style={{ display: "flex", gap: 20, marginTop: 8, fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
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