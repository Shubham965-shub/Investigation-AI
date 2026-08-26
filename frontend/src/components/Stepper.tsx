import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";

export type StepStatus = "completed" | "in-progress" | "open";

export interface StepDef {
  key: string;
  label: string;
  path: string | null;
}

export const RECORD_STEPS: StepDef[] = [
  { key: "problem-statement", label: "Problem Statement", path: "problem-statement" },
  { key: "evidence-collection", label: "Evidence Collection", path: "evidence-collection" },
  { key: "interview-questionnaire", label: "Interview Questionnaire", path: "interview-questionnaire" },
  { key: "rci-plan", label: "RCI Plan Creation", path: "rci-plan" },
  { key: "task-critique", label: "Task Critique", path: "task-critique" },
  { key: "rc-capa-critique", label: "RC, Impact & CAPA Critique", path: "rc-capa-critique" },
  { key: "rci-report", label: "RCI Report", path: "rci-report" },
];

function circleStyle(status: StepStatus): React.CSSProperties {
  if (status === "completed") {
    return { background: "var(--color-completed-bg)", border: "2px solid var(--color-completed-border)", color: "var(--color-primary)" };
  }
  if (status === "in-progress") {
    return { background: "var(--color-primary)", border: "2px solid var(--color-primary)", color: "#fff" };
  }
  return { background: "var(--color-open-bg)", border: "2px solid var(--color-open-border)", color: "var(--color-text-muted)" };
}

function labelColor(status: StepStatus): string {
  return status === "open" ? "var(--color-text-muted)" : "var(--color-primary-text)";
}

// What actually happens off-screen between these two step pairs — the app
// itself has no workflow for it, so the person icon on the connecting line
// explains it on hover (2026-08-26, per the user).
const CONNECTOR_NOTES: Record<number, string[]> = {
  3: [
    "RCI Plan is taken to SIT Lead for review and signoff",
    "Approved RCI Plan is uploaded to TW",
    "Tasks are given to appropriate Task Owners",
    "Task Owners create Reports for their tasks",
    "Task Reports are uploaded to Athena for Critique",
  ],
  4: [
    "Critiqued Task Reports are uploaded to Database",
    "RC, Impact & CAPA Report is created",
    "RC, Impact & CAPA Report is uploaded to Athena for Critique",
  ],
};

// Hover-only popover anchored to the connector's person icon, portaled to
// document.body (position: fixed) so it isn't clipped by any ancestor's
// overflow and never nudges the stepper's own layout.
function ConnectorPersonIcon({ color, notes }: { color: string; notes: string[] }) {
  const [hovered, setHovered] = useState(false);
  const [rect, setRect] = useState<{ left: number; top: number } | null>(null);
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const hideTimeout = useRef<number | null>(null);

  function show() {
    if (hideTimeout.current !== null) {
      window.clearTimeout(hideTimeout.current);
      hideTimeout.current = null;
    }
    const r = anchorRef.current?.getBoundingClientRect();
    if (r) setRect({ left: r.left + r.width / 2, top: r.bottom });
    setHovered(true);
  }

  function scheduleHide() {
    hideTimeout.current = window.setTimeout(() => setHovered(false), 150);
  }

  return (
    <span
      ref={anchorRef}
      onMouseEnter={show}
      onMouseLeave={scheduleHide}
      style={{ position: "relative", display: "inline-flex", flexShrink: 0, margin: "0 6px" }}
    >
      {/* Absolutely positioned so it doesn't add height to the connector row
          (which would throw off the dotted lines' vertical centering on the
          icon itself) (2026-08-26, per the user). */}
      <span
        style={{
          position: "absolute",
          bottom: "100%",
          left: "50%",
          transform: "translateX(-50%)",
          marginBottom: 4,
          whiteSpace: "nowrap",
          fontSize: "var(--font-size-xs)",
          fontWeight: 600,
          color: "var(--color-text-muted)",
        }}
      >
        Manual Input
      </span>
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="8" r="4" />
        <path d="M4 20c0-4.4 3.6-7 8-7s8 2.6 8 7" />
      </svg>

      {rect &&
        createPortal(
          <div
            onMouseEnter={show}
            onMouseLeave={scheduleHide}
            style={{
              position: "fixed",
              top: rect.top + 10,
              left: Math.min(Math.max(rect.left - 150, 16), window.innerWidth - 316),
              width: 300,
              zIndex: 1000,
              opacity: hovered ? 1 : 0,
              visibility: hovered ? "visible" : "hidden",
              transform: hovered ? "translateY(0)" : "translateY(-4px)",
              transition: "opacity 150ms ease, transform 150ms ease",
              pointerEvents: hovered ? "auto" : "none",
              background: "var(--color-surface)",
              border: "1px solid var(--color-card-border)",
              borderRadius: 10,
              boxShadow: "0 12px 32px rgba(0,0,0,0.18)",
              padding: "14px 16px",
            }}
          >
            <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 6 }}>
              {notes.map((note, i) => (
                <li key={i} style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text)", lineHeight: 1.4 }}>
                  {note}
                </li>
              ))}
            </ul>
          </div>,
          document.body
        )}
    </span>
  );
}

export function Stepper({
  recordId,
  currentStep,
  stepStatuses,
  eventType,
}: {
  recordId: string;
  currentStep: string;
  stepStatuses: Record<string, StepStatus>;
  // Market Complaint investigations can skip straight from Evidence
  // Collection to RCI Plan Creation without completing Interview
  // Questionnaire (2026-08-19, per the user) — RCI Plan Creation's own
  // gating already never required it, so this is purely a visual "this step
  // is optional" marker, not a real lock (nothing in this stepper actually
  // blocks navigation today).
  eventType?: string;
}) {
  const navigate = useNavigate();

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}>
      {RECORD_STEPS.map((step, index) => {
        const status = stepStatuses[step.key] ?? "open";
        const isLast = index === RECORD_STEPS.length - 1;
        const clickable = step.path !== null;
        const isSkippable = step.key === "interview-questionnaire" && eventType === "Market Complaint";
        // Small human-symbol marker between RCI Plan Creation (4) & Task
        // Critique (5), and between Task Critique (5) & RC & CAPA Critique
        // (6) (2026-08-26, per the user) — purely a visual marker on the
        // connecting line, framed by dotted segments on both sides instead
        // of the usual solid line.
        const hasConnectorBox = index === 3 || index === 4;
        const lineColor = status === "completed" ? "var(--color-primary)" : "var(--color-open-border)";

        return (
          <div key={step.key} style={{ display: "flex", alignItems: "center", flex: isLast ? "0 0 auto" : "1 1 auto" }}>
            <div
              onClick={() => clickable && navigate(`/records/${recordId}/${step.path}`)}
              style={{ display: "flex", flexDirection: "column", alignItems: "center", cursor: clickable ? "pointer" : "default" }}
            >
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "var(--font-size-md)",
                  fontWeight: step.key === currentStep ? 700 : 400,
                  ...circleStyle(status),
                }}
              >
                {index + 1}
              </div>
              <div
                style={{
                  marginTop: 12,
                  fontSize: "var(--font-size-base)",
                  fontWeight: 600,
                  color: labelColor(status),
                  whiteSpace: "nowrap",
                }}
              >
                {step.label}
                {isSkippable && (
                  <span style={{ display: "block", fontWeight: 400, fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                    (Optional)
                  </span>
                )}
              </div>
            </div>
            {!isLast && (hasConnectorBox ? (
              <div style={{ display: "flex", alignItems: "center", flex: 1, margin: "0 8px 24px" }}>
                <div style={{ flex: 1, height: 0, borderTop: `2px dotted ${lineColor}` }} />
                <ConnectorPersonIcon color={lineColor} notes={CONNECTOR_NOTES[index]} />
                <div style={{ flex: 1, height: 0, borderTop: `2px dotted ${lineColor}` }} />
              </div>
            ) : (
              <div
                style={{
                  height: 2,
                  flex: 1,
                  margin: "0 8px 24px",
                  background: lineColor,
                }}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
