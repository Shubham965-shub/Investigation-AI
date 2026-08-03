// Explains how an investigation's status (On Track / At Risk / Overdue /
// Closed) is derived from days-open + criticality — content per the
// reference InvestigationStatus.jsx the user supplied, restyled to the
// app's own theme tokens/semantic colors (matching ActionCenterPage.css's
// .ac-status-card / .ac-badge palette) instead of the reference's hardcoded
// light-mode-only colors, so it reads correctly in dark mode too.

type StatusKey = "On Track" | "At Risk" | "Overdue" | "Closed";

const STATUS_DOT_COLOR: Record<StatusKey, string> = {
  "On Track": "var(--color-success-text)",
  "At Risk": "var(--color-warning-text)",
  Overdue: "var(--color-danger-text)",
  Closed: "var(--color-text-muted)",
};

interface CriticalityConfig {
  title: string;
  badgeBg: string;
  badgeText: string;
  thresholds: { status: StatusKey; label: string }[];
}

const CRITICALITY_CONFIG: CriticalityConfig[] = [
  {
    title: "Critical",
    badgeBg: "var(--color-danger-bg)",
    badgeText: "var(--color-danger-text)",
    thresholds: [
      { status: "On Track", label: "0 – 7 days open" },
      { status: "At Risk", label: "8 – 15 days open" },
      { status: "Overdue", label: "> 15 days open" },
      { status: "Closed", label: "Closed" },
    ],
  },
  {
    title: "Non-Critical",
    badgeBg: "var(--color-info-bg)",
    badgeText: "var(--color-info-text)",
    thresholds: [
      { status: "On Track", label: "0 – 11 days open" },
      { status: "At Risk", label: "12 – 19 days open" },
      { status: "Overdue", label: "> 19 days open" },
      { status: "Closed", label: "Closed" },
    ],
  },
];

const LEGEND_ORDER: StatusKey[] = ["On Track", "At Risk", "Overdue", "Closed"];

function StatusDot({ status }: { status: StatusKey }) {
  return (
    <span
      style={{ width: 8, height: 8, borderRadius: "50%", background: STATUS_DOT_COLOR[status], display: "inline-block", flexShrink: 0 }}
    />
  );
}

function CriticalityCard({ title, badgeBg, badgeText, thresholds }: CriticalityConfig) {
  return (
    <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-card-border)", borderRadius: 8, overflow: "hidden", flex: 1, minWidth: 200 }}>
      <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--color-card-border)", display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ background: badgeBg, color: badgeText, fontSize: "var(--font-size-xs)", fontWeight: 600, padding: "3px 10px", borderRadius: 20 }}>
          {title}
        </span>
        <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>investigations</span>
      </div>
      <div>
        {thresholds.map(({ status, label }, i) => (
          <div key={status}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px" }}>
              <StatusDot status={status} />
              <div>
                <div style={{ fontSize: "var(--font-size-sm)", fontWeight: 600, color: "var(--color-text)" }}>{status}</div>
                <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)", marginTop: 1 }}>{label}</div>
              </div>
            </div>
            {i < thresholds.length - 1 && (
              <hr style={{ margin: "0 14px", border: "none", borderTop: "1px solid var(--color-card-border)" }} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 14 }}>
      {LEGEND_ORDER.map((status) => (
        <span key={status} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
          <span style={{ width: 9, height: 9, borderRadius: 2, background: STATUS_DOT_COLOR[status], display: "inline-block" }} />
          {status}
        </span>
      ))}
    </div>
  );
}

export function InvestigationStatusInfo() {
  return (
    <div style={{ width: 460, maxWidth: "80vw" }}>
      <p style={{ margin: "0 0 4px", fontWeight: 700, fontSize: "var(--font-size-base)", color: "var(--color-text)" }}>Investigation Status Thresholds</p>
      <p style={{ margin: "0 0 12px", fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
        How an investigation's status is determined, based on days open and criticality.
      </p>
      <Legend />
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {CRITICALITY_CONFIG.map((config) => (
          <CriticalityCard key={config.title} {...config} />
        ))}
      </div>
    </div>
  );
}