import { useState } from "react";
import modalClose from "../assets/icons/modal-close.svg";

// .field-value's global height is fixed at 3 lines for multi-line fields elsewhere; these are single-line, so reset height to natural size.
const NORMAL_FIELD_STYLE = { height: "auto", overflowY: "visible" as const };

export function ChangePasswordDialog({
  submitting,
  error,
  onCancel,
  onConfirm,
}: {
  submitting: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: (fields: { currentPassword: string; newPassword: string }) => void;
}) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const mismatch = confirmPassword.length > 0 && newPassword !== confirmPassword;

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!currentPassword || newPassword.length < 8 || newPassword !== confirmPassword) return;
    onConfirm({ currentPassword, newPassword });
  }

  return (
    <>
      <div onClick={onCancel} style={{ position: "fixed", inset: 0, background: "rgba(73, 84, 80, 0.45)", zIndex: 60 }} />
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
          width: "min(480px, 92vw)",
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
          <p style={{ margin: 0, fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: "var(--font-size-lg)", color: "var(--color-text)" }}>
            Change Password
          </p>
          <button type="button" aria-label="Close" onClick={onCancel} style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}>
            <img src={modalClose} alt="" width={20} height={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16, padding: 24 }}>
          <div>
            <p className="field-label">
              Current Password <span style={{ color: "var(--color-danger-text)" }}>*</span>
            </p>
            <input
              className="field-value"
              style={NORMAL_FIELD_STYLE}
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div>
            <p className="field-label">
              New Password <span style={{ color: "var(--color-danger-text)" }}>*</span>
            </p>
            <input
              className="field-value"
              style={NORMAL_FIELD_STYLE}
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="At least 8 characters"
              minLength={8}
              required
            />
          </div>

          <div>
            <p className="field-label">
              Confirm New Password <span style={{ color: "var(--color-danger-text)" }}>*</span>
            </p>
            <input
              className="field-value"
              style={NORMAL_FIELD_STYLE}
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />
            {mismatch && <p className="error-banner">Passwords don't match</p>}
          </div>

          {error && <p className="error-banner">{error}</p>}

          <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
            <button type="button" className="btn-outline" onClick={onCancel} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={submitting || mismatch || newPassword.length < 8}>
              {submitting ? "Changing…" : "Change Password"}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
