import modalClose from "../assets/icons/modal-close.svg";
import { BoldText } from "./BoldText";
import { formatAttemptTimestamp } from "../utils/formatTimestamp";
import type { RcCapaReport } from "../api/dashboard";

const CATEGORY_LABEL: Record<"rc_impact" | "capa", string> = {
  rc_impact: "RC Impact Assessment Critique",
  capa: "CAPA Critique",
};

const DECISION_LABEL: Record<"pending" | "accepted" | "rejected", string> = {
  pending: "Pending",
  accepted: "Accepted",
  rejected: "Rejected",
};

// Full audit trail across every RC & CAPA Critique attempt — unlike Task
// Critique, investigation_rc_capa_reports already keeps a real row per
// attempt, so this is just every report, oldest first. Independent of lock/
// complete state (2026-08-18, per the user) — shown behind its own button
// in a separate panel rather than inline, since it's the whole history, not
// just the current report.
export function RcCapaHistoryPanel({ reports, loading, onClose }: { reports: RcCapaReport[]; loading: boolean; onClose: () => void }) {
  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(73, 84, 80, 0.45)", zIndex: 60 }} />
      <div
        role="dialog"
        aria-modal="true"
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          background: "var(--color-surface)",
          borderRadius: 10,
          width: "min(720px, 92vw)",
          maxHeight: "85vh",
          overflowY: "auto",
          padding: "32px 32px 24px",
          zIndex: 61,
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          style={{ position: "absolute", top: 20, right: 20, background: "none", border: "none", cursor: "pointer", padding: 0 }}
        >
          <img src={modalClose} alt="" width={20} height={20} />
        </button>

        <p style={{ margin: 0, fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: "var(--font-size-lg)", color: "var(--color-text)" }}>
          Recommendation History
        </p>

        {loading && <p style={{ margin: 0, color: "var(--color-text-muted)" }}>Loading history…</p>}
        {!loading && reports.length === 0 && <p style={{ margin: 0, color: "var(--color-text-muted)" }}>No attempts uploaded yet.</p>}

        {reports.map((report) => (
          <div key={report.id} style={{ border: "1px solid var(--color-card-border)", borderRadius: 10, overflow: "hidden" }}>
            <div style={{ background: "var(--color-bg)", borderBottom: "1px solid var(--color-card-border)", padding: "13px 17px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontWeight: 600, fontSize: "var(--font-size-base)" }}>
                Attempt {report.attempt_number} — {report.file_name}
              </span>
              <span style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
                {formatAttemptTimestamp(report.uploaded_at)}
              </span>
            </div>
            <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
              {report.is_gospel ? (
                <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
                  Accepted as final — no recommendations were generated for it.
                </p>
              ) : (
                report.critiques.map((critique) => (
                  <div key={critique.category} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-sm)" }}>{CATEGORY_LABEL[critique.category]}</p>
                    {critique.summary && (
                      <p style={{ margin: 0, fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                        <BoldText text={critique.summary} />
                      </p>
                    )}
                    {critique.recommendations.length > 0 && (
                      <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 4 }}>
                        {critique.recommendations.map((rec) => (
                          <li key={rec.id} style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                            {rec.description}{" "}
                            <span
                              style={{
                                fontWeight: 600,
                                color:
                                  rec.decision === "accepted"
                                    ? "var(--color-success-text)"
                                    : rec.decision === "rejected"
                                      ? "var(--color-danger-text)"
                                      : "var(--color-text-muted)",
                              }}
                            >
                              ({DECISION_LABEL[rec.decision]})
                            </span>
                            {rec.reason && ` — ${rec.reason}`}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}