export type ScoringReason = "all_decided" | "gospel" | "final_attempt";

const MESSAGE: Record<ScoringReason, string> = {
  all_decided: "Every recommendation has been accepted or rejected — this report is now final and is being scored.",
  gospel: "This upload is being accepted as the final report with no further critique — it's being scored now.",
  final_attempt: "This is the final upload attempt — no further review is possible, and it's being scored now.",
};

// Shown while the finalizing request also runs DS's rubric scoring server-side. Not dismissable; `reason` is fixed client-side at submit time so the message can't misrepresent which finalize path triggered it.
export function ScoringDialog({ reason }: { reason: ScoringReason }) {
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
          Scoring in progress…
        </p>
        <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>{MESSAGE[reason]}</p>
      </div>
    </>
  );
}