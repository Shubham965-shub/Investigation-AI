import modalClose from "../assets/icons/modal-close.svg";

// Generic "are you sure" confirmation modal — matches Figma node 1490-11504
// ("Accept Evidence Collection?"). Used by Evidence Collection and Interview
// Questionnaire's "Agree & Copy" button before locking the module and moving
// to the next step.
export function ConfirmDialog({
  title,
  message,
  onCancel,
  onConfirm,
}: {
  title: string;
  // Optional (2026-08-21, per the user) — Evidence Collection/Interview
  // Questionnaire's confirm dialogs no longer show a message, just the
  // title; RCI Plan's still does.
  message?: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <>
      <div onClick={onCancel} style={{ position: "fixed", inset: 0, background: "rgba(73, 84, 80, 0.45)", zIndex: 60 }} />
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
          width: "min(560px, 92vw)",
          padding: "40px 32px 32px",
          zIndex: 61,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 20,
          textAlign: "center",
        }}
      >
        <button
          type="button"
          aria-label="Close"
          onClick={onCancel}
          style={{ position: "absolute", top: 20, right: 20, background: "none", border: "none", cursor: "pointer", padding: 0 }}
        >
          <img src={modalClose} alt="" width={20} height={20} />
        </button>

        <p style={{ margin: 0, fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: "var(--font-size-hero)", lineHeight: 1.3, color: "var(--color-text)" }}>
          {title}
        </p>
        {message && <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)", maxWidth: 420 }}>{message}</p>}

        <div style={{ display: "flex", gap: 16, marginTop: 8, width: "100%", justifyContent: "center" }}>
          <button type="button" className="btn-outline" style={{ flex: "0 1 190px", padding: "12px 0", justifyContent: "center" }} onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn-primary" style={{ flex: "0 1 190px", padding: "12px 0" }} onClick={onConfirm}>
            Yes
          </button>
        </div>
      </div>
    </>
  );
}
