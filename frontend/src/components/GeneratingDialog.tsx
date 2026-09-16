// Not dismissable, same as ScoringDialog — shown during long ds-agent-backed generation calls.
export function GeneratingDialog({ heading, message }: { heading: string; message: string }) {
  return (
    <>
      <div style={{ position: "fixed", inset: 0, background: "rgba(73, 84, 80, 0.45)", zIndex: 60 }} />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-busy="true"
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          background: "var(--color-surface)",
          borderRadius: 10,
          width: "min(440px, 92vw)",
          padding: "36px 32px",
          zIndex: 61,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 16,
          textAlign: "center",
        }}
      >
        <span className="spinner" style={{ width: 28, height: 28, borderWidth: 3, color: "var(--color-primary)" }} />
        <p style={{ margin: 0, fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: "var(--font-size-lg)", color: "var(--color-text)" }}>
          {heading}
        </p>
        <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>{message}</p>
      </div>
    </>
  );
}
