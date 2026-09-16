import { useState } from "react";
import modalClose from "../assets/icons/modal-close.svg";

// Single name field only — EC/IQ don't need the full multi-field form (Description/Type/etc).
export function AddItemDialog({
  title,
  label,
  placeholder,
  confirmLabel,
  onCancel,
  onConfirm,
}: {
  title: string;
  label: string;
  placeholder: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: (name: string) => void;
}) {
  const [name, setName] = useState("");

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    onConfirm(trimmed);
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
          width: "min(560px, 92vw)",
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
            {title}
          </p>
          <button type="button" aria-label="Close" onClick={onCancel} style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}>
            <img src={modalClose} alt="" width={20} height={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 20, padding: 24 }}>
          <div>
            <p className="field-label">
              {label} <span style={{ color: "var(--color-danger-text)" }}>*</span>
            </p>
            <input
              className="field-value"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={placeholder}
              required
              autoFocus
            />
          </div>

          <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
            <button type="button" className="btn-outline" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="btn-primary">
              {confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
