import modalClose from "../assets/icons/modal-close.svg";

// Plain acknowledgment (one button, not a confirmation) shown once every recommendation has been decided.
export function IncorporateChangesDialog({ onClose }: { onClose: () => void }) {
  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(73, 84, 80, 0.45)", zIndex: 60 }} />
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
          onClick={onClose}
          style={{ position: "absolute", top: 20, right: 20, background: "none", border: "none", cursor: "pointer", padding: 0 }}
        >
          <img src={modalClose} alt="" width={20} height={20} />
        </button>

        <p style={{ margin: 0, fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: "var(--font-size-lg)", lineHeight: 1.3, color: "var(--color-text)" }}>
          Please incorporate recommended changes
        </p>

        <button type="button" className="btn-primary" style={{ flex: "0 1 190px", padding: "12px 0" }} onClick={onClose}>
          OK
        </button>
      </div>
    </>
  );
}
