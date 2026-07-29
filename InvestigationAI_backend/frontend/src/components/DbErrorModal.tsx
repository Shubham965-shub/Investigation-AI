import { useNavigate } from "react-router-dom";

// Blocking modal shown when the DB fetch for a record genuinely fails (not a
// 404 — that means "no record yet" and is a valid, non-blocking state). No
// way to dismiss and proceed with a broken/incomplete view; only retry or
// leave.
export function DbErrorModal({ message, onRetry }: { message: string; onRetry: () => void }) {
  const navigate = useNavigate();

  return (
    <>
      <div style={{ position: "fixed", inset: 0, background: "rgba(73, 84, 80, 0.45)", zIndex: 60 }} />
      <div
        role="alertdialog"
        aria-modal="true"
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          background: "var(--color-surface)",
          borderRadius: 10,
          width: "min(480px, 92vw)",
          padding: 24,
          zIndex: 61,
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <p style={{ margin: 0, fontWeight: 700, fontSize: 20, color: "var(--color-text)" }}>
          Unable to load this investigation
        </p>
        <p style={{ margin: 0, fontSize: 14, color: "var(--color-text-muted)" }}>{message}</p>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
          <button type="button" className="btn-outline" onClick={() => navigate("/")}>
            Back to Investigations
          </button>
          <button type="button" className="btn-primary" onClick={onRetry}>
            Retry
          </button>
        </div>
      </div>
    </>
  );
}
