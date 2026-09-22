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
  { key: "data-interpretation", label: "Data Interpretation", path: "data-interpretation" },
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

// Cumulative day ranges from investigation initiation, not from each stage's own local anchor — later stages compound the prior stage's deadline (source table counts each stage from the PRIOR stage's deadline, not from initiation directly).
type StepSla = string | { critical: string; other: string };
const STEP_SLA: Record<string, StepSla> = {
  "problem-statement": "Day 0–1",
  "evidence-collection": { critical: "Day 0–2", other: "Day 0–2" },
  "interview-questionnaire": { critical: "Day 0–2", other: "Day 0–2" },
  "rci-plan": { critical: "Day 0–2", other: "Day 0–2" },
  "task-critique": { critical: "Day 2–10", other: "Day 2–10" },
  "rc-capa-critique": { critical: "Day 10–13", other: "Day 10-13" },
  "rci-report": { critical: "Day 13–15", other: "Day 13-15" },
};

// Shows only the applicable tier when known; both (unlabeled) when criticality couldn't be determined.
function renderStepSla(entry: StepSla, tier: "critical" | "other" | null | undefined) {
  if (typeof entry === "string") return entry;
  if (tier === "critical") return entry.critical;
  if (tier === "other") return entry.other;
  return (
    <>
      <div>{entry.critical}</div>
      <div style={{ marginTop: 4 }}>{entry.other}</div>
    </>
  );
}

// Native-tooltip fallback so the full figure is reachable when the 2-line clamp above ellipsizes it.
function slaTitle(entry: StepSla, tier: "critical" | "other" | null | undefined): string | undefined {
  if (typeof entry === "string") return entry;
  if (tier === "critical") return entry.critical;
  if (tier === "other") return entry.other;
  return `${entry.critical} / ${entry.other}`;
}

// What happens off-screen between these step pairs — no in-app workflow for it, so the connector's person icon explains it on hover.
// Indices shifted by 1 (2026-09-22) to account for the new Data Interpretation step inserted at index 4 — the
// offline SIT Lead review still happens after RCI Plan Creation's in-app work is done, which now finishes at
// Data Interpretation (index 4) rather than RCI Plan Creation (index 3) itself.
const CONNECTOR_NOTES: Record<number, string[]> = {
  4: [
    "RCI Plan is taken to SIT Lead for review and signoff",
    "Approved RCI Plan is uploaded to TW",
    "Tasks are given to appropriate Task Owners",
    "Task Owners create Reports for their tasks",
    "Task Reports are uploaded to Athena for Critique",
  ],
  5: [
    "Critiqued Task Reports are uploaded to Database",
    "RC, Impact & CAPA Report is created",
    "RC, Impact & CAPA Report is uploaded to Athena for Critique",
  ],
};

// Portaled to document.body (position: fixed) so it isn't clipped by any ancestor's overflow and never nudges the stepper's layout.
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
      {/* Absolutely positioned so it doesn't add height to the connector row and throw off the dotted lines' centering. */}
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
  slaTier,
}: {
  recordId: string;
  currentStep: string;
  stepStatuses: Record<string, StepStatus>;
  // Market Complaint can skip Interview Questionnaire — purely a visual "optional" marker, not a real lock (nothing here blocks navigation).
  eventType?: string;
  // null/undefined shows both tiers (unknown criticality).
  slaTier?: "critical" | "other" | null;
}) {
  const navigate = useNavigate();

  return (
    // paddingBottom reserves room for each step's absolutely-positioned label+SLA text (no longer part of row height); paddingLeft/Right keeps first/last step's centered label from running off the page edge.
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        width: "100%",
        padding: "0 90px 60px",
        position: "sticky",
        top: 0,
        zIndex: 5,
        background: "var(--color-bg)",
      }}
    >
      {RECORD_STEPS.map((step, index) => {
        const status = stepStatuses[step.key] ?? "open";
        const isLast = index === RECORD_STEPS.length - 1;
        const clickable = step.path !== null;
        const isSkippable = step.key === "interview-questionnaire" && eventType === "Market Complaint";
        // Visual marker (dotted line + person icon) between steps 4-5 and 5-6, instead of the usual solid line.
        const hasConnectorBox = index === 4 || index === 5;
        const lineColor = status === "completed" ? "var(--color-primary)" : "var(--color-open-border)";

        return (
          <div key={step.key} style={{ display: "flex", alignItems: "flex-start", flex: isLast ? "0 0 auto" : "1 1 auto" }}>
            <div
              onClick={() => clickable && navigate(`/records/${recordId}/${step.path}`)}
              style={{ position: "relative", display: "flex", flexDirection: "column", alignItems: "center", cursor: clickable ? "pointer" : "default" }}
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
              {/* Absolutely positioned so a long label/SLA line doesn't widen this step's box and crowd the connecting line. */}
              <div
                style={{
                  position: "absolute",
                  top: "100%",
                  left: "50%",
                  transform: "translateX(-50%)",
                  marginTop: 12,
                  width: "max-content",
                  maxWidth: 170,
                  fontSize: "var(--font-size-base)",
                  fontWeight: 600,
                  color: labelColor(status),
                  whiteSpace: "nowrap",
                  textAlign: "center",
                }}
              >
                {step.label}
                {isSkippable && (
                  <span style={{ display: "block", fontWeight: 400, fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                    (Optional)
                  </span>
                )}
                {STEP_SLA[step.key] && (
                  <div
                    title={slaTitle(STEP_SLA[step.key], slaTier)}
                    style={{
                      marginTop: 2,
                      fontWeight: 400,
                      fontSize: "var(--font-size-xs)",
                      color: "var(--color-text-muted)",
                      whiteSpace: "normal",
                      maxWidth: 170,
                      textAlign: "center",
                      lineHeight: 1.3,
                      // Hard-capped at 2 lines; ellipsis is the fallback for text too long to fit.
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {renderStepSla(STEP_SLA[step.key], slaTier)}
                  </div>
                )}
              </div>
            </div>
            {/* marginTop centers the connector on the 48px circle (fixed at 24px from row top) regardless of how much SLA text trails below it. */}
            {!isLast && (hasConnectorBox ? (
              <div style={{ display: "flex", alignItems: "center", flex: 1, margin: "10px 2px 0" }}>
                <div style={{ flex: 1, height: 0, borderTop: `2px dotted ${lineColor}` }} />
                <ConnectorPersonIcon color={lineColor} notes={CONNECTOR_NOTES[index]} />
                <div style={{ flex: 1, height: 0, borderTop: `2px dotted ${lineColor}` }} />
              </div>
            ) : (
              <div
                style={{
                  height: 2,
                  flex: 1,
                  margin: "23px 2px 0",
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
