import { useEffect, useState } from "react";
import modalClose from "../assets/icons/modal-close.svg";
import { ApiError } from "../api/client";
import { getAuditTrail, type AuditTrailEntry } from "../api/auth";

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function AuditTrailModal({
  recordId,
  rciSegment,
  onClose,
}: {
  recordId: string;
  rciSegment: string;
  onClose: () => void;
}) {
  const [entries, setEntries] = useState<AuditTrailEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAuditTrail(recordId, rciSegment)
      .then((data) => {
        if (!cancelled) setEntries(data.entries);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? String(err.detail) : "Failed to load audit trail");
      });
    return () => {
      cancelled = true;
    };
  }, [recordId, rciSegment]);

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
          width: "min(900px, 92vw)",
          maxHeight: "80vh",
          zIndex: 61,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "20px 24px",
            borderBottom: "1px solid var(--color-card-border)",
          }}
        >
          <div>
            <p style={{ margin: 0, fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: "var(--font-size-lg)", color: "var(--color-text)" }}>
              Audit Trail
            </p>
            <p style={{ margin: "2px 0 0", fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
              Record {recordId}{rciSegment !== "none" ? ` / RCI ${rciSegment}` : ""}
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}>
            <img src={modalClose} alt="" width={20} height={20} />
          </button>
        </div>

        <div style={{ padding: 24, overflowY: "auto" }}>
          {error && <p className="error-banner">{error}</p>}
          {!error && !entries && <p style={{ margin: 0, color: "var(--color-text-muted)" }}>Loading…</p>}
          {!error && entries && entries.length === 0 && (
            <p style={{ margin: 0, color: "var(--color-text-muted)" }}>No recorded activity for this record yet.</p>
          )}
          {!error && entries && entries.length > 0 && (
            <table className="ac-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Person</th>
                  <th>Role</th>
                  <th>Action</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e, i) => (
                  <tr key={i}>
                    <td style={{ whiteSpace: "nowrap" }}>{formatTimestamp(e.created_at)}</td>
                    <td>{e.full_name ?? e.username ?? "—"}</td>
                    <td>{e.role ?? "—"}</td>
                    <td style={{ fontFamily: "monospace", fontSize: "var(--font-size-xs)" }}>
                      {e.method} {e.path}
                    </td>
                    <td>
                      {e.status_code ?? "—"}
                      {e.duration_ms != null && (
                        <span style={{ color: "var(--color-text-muted)" }}> ({e.duration_ms}ms)</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}
