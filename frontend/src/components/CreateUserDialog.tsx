import { useState } from "react";
import modalClose from "../assets/icons/modal-close.svg";

// .field-value's global height (calc(1.4em * 3 + 18px)) is fixed at 3 lines
// tall, for the multi-line/grid text fields it was designed for elsewhere
// (2026-09-08, per the user) — these are single-line inputs/a select, so
// they don't need to obey that constraint; just override the height back
// to the element's own natural size, keeping the rest of .field-value's
// look (background/border/padding/font).
const NORMAL_FIELD_STYLE = { height: "auto", overflowY: "visible" as const };

// Full Name/Username(email)/Password/Role form — same modal chrome as
// AddItemDialog (top-left title + top-right X, bordered body, bottom-right
// Cancel/primary footer), just a 4-field form instead of a single name
// field (2026-09-08, per the user — User Management's "Create User" action).
export function CreateUserDialog({
  roles,
  submitting,
  error,
  onCancel,
  onConfirm,
}: {
  roles: string[];
  submitting: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: (fields: { fullName: string; username: string; password: string; role: string }) => void;
}) {
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(roles[0] ?? "");

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!fullName.trim() || !username.trim() || !password || !role) return;
    onConfirm({ fullName: fullName.trim(), username: username.trim(), password, role });
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
            Create User
          </p>
          <button type="button" aria-label="Close" onClick={onCancel} style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}>
            <img src={modalClose} alt="" width={20} height={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16, padding: 24 }}>
          <div>
            <p className="field-label">
              Full Name <span style={{ color: "var(--color-danger-text)" }}>*</span>
            </p>
            <input
              className="field-value"
              style={NORMAL_FIELD_STYLE}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="e.g. Jane Doe"
              required
              autoFocus
            />
          </div>

          <div>
            <p className="field-label">
              Email / Username <span style={{ color: "var(--color-danger-text)" }}>*</span>
            </p>
            <input
              className="field-value"
              style={NORMAL_FIELD_STYLE}
              type="email"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. jane.doe@strides.com"
              required
            />
          </div>

          <div>
            <p className="field-label">
              Password <span style={{ color: "var(--color-danger-text)" }}>*</span>
            </p>
            <input
              className="field-value"
              style={NORMAL_FIELD_STYLE}
              type="text"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              minLength={8}
              required
            />
          </div>

          <div>
            <p className="field-label">
              Role <span style={{ color: "var(--color-danger-text)" }}>*</span>
            </p>
            <select
              className="field-value"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              required
              style={{ ...NORMAL_FIELD_STYLE, width: "100%" }}
            >
              {roles.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          {error && <p className="error-banner">{error}</p>}

          <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
            <button type="button" className="btn-outline" onClick={onCancel} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? "Creating…" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
