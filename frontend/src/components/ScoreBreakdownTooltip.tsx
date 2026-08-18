import type { ScoreBreakdownTable } from "../api/dashboard";
import { InfoTooltip } from "./InfoTooltip";

const COLUMN_HEADERS = ["ID", "Checkpoint", "Max", "Verdict", "Score", "Rationale (why)", "Evidence quote"];

function verdictColor(verdict: string): string {
  const v = verdict.toLowerCase();
  if (v === "yes") return "var(--color-success-text)";
  if (v === "no") return "var(--color-danger-text)";
  return "var(--color-text-muted)";
}

// Full per-checkpoint breakdown for one or more scored sections (e.g. just
// "task_report" for Task Critique, or "rc"+"impact" together for RC & CAPA's
// combined RC score) — shown via a small info icon next to the generated
// score (2026-08-14, per the user), same rows/columns as ds's own marking-
// checklist spreadsheet (ID/Checkpoint/Max/Verdict/Score/Rationale/Evidence).
export function ScoreBreakdownTooltip({ tables }: { tables: ScoreBreakdownTable[] }) {
  if (tables.length === 0) return null;

  return (
    <InfoTooltip label="Score breakdown" width={880}>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {tables.map((table, i) => (
          <div key={`${table.section}-${i}`}>
            <p style={{ margin: 0, fontWeight: 700, fontSize: "var(--font-size-md)" }}>
              {table.label} (/{table.native_max})
            </p>
            <div
              style={{
                background: "var(--color-open-bg)",
                border: "1px solid var(--color-card-border)",
                borderRadius: 4,
                padding: "4px 8px",
                margin: "4px 0 8px",
                display: "inline-block",
                fontWeight: 600,
                fontSize: "var(--font-size-sm)",
              }}
            >
              {table.marks_awarded} ({table.percentage.toFixed(1)}%)
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 720, fontSize: "var(--font-size-xs)" }}>
                <thead>
                  <tr>
                    {COLUMN_HEADERS.map((header) => (
                      <th
                        key={header}
                        style={{
                          background: "var(--color-header-bg)",
                          color: "#fafafa",
                          textAlign: "left",
                          padding: "6px 8px",
                          fontWeight: 700,
                          whiteSpace: "nowrap",
                        }}
                      >
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((row) => (
                    <tr key={row.id} style={{ borderBottom: "1px solid var(--color-card-border)" }}>
                      <td style={{ padding: "6px 8px", verticalAlign: "top", whiteSpace: "nowrap" }}>{row.id}</td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top", minWidth: 200 }}>{row.checkpoint}</td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top", whiteSpace: "nowrap" }}>{row.max}</td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top", whiteSpace: "nowrap", fontWeight: 600, color: verdictColor(row.verdict) }}>
                        {row.verdict}
                      </td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top", whiteSpace: "nowrap" }}>{row.score}</td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top", minWidth: 220, color: "var(--color-text-muted)" }}>{row.rationale}</td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top", minWidth: 180, color: "var(--color-text-muted)" }}>{row.evidence_quote}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </InfoTooltip>
  );
}