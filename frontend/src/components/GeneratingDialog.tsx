// Shown while a slow, ds-agent-backed generation call is in flight — e.g.
// Evidence Collection's POST /evidence/{id}/collect or Interview
// Questionnaire's POST /questionnaire/{id}/generate, both of which proxy to
// ds and previously only showed a plain line of muted text with no visual
// indication of an in-progress, non-trivial wait (2026-09-08, per the user).
// Not dismissable — same non-cancelable spirit as ScoringDialog, which this
// mirrors exactly (same overlay/box/spinner structure), just for a
// generation call instead of a scoring one.
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
