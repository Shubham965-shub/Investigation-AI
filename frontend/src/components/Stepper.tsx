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

// SLA target shown under each step's own label (2026-08-26, per the user) —
// keyed by step, not by connector, since a couple of source stages
// ("Evidence Collection and Interview Questionnaire") span two modules and
// repeat verbatim under both. Phrased as a cumulative day range from the
// investigation's own initiation — not from each stage's own local anchor
// (2026-08-26, per the user: "not from its own anchor event") — since the
// source table's later stages (Task Execution, Report Generation, Report
// Sign Off) each count from the PRIOR stage's own deadline rather than from
// initiation directly, the day range compounds: e.g. critical-tier Task
// Execution is "within 8 days from RCI Plan sign-off", and RCI Plan sign-off
// is itself "within 3 days from initiation", so Task Execution's cumulative
// window from initiation is day 3 through day 11, not 0 through 8. The two
// tiers only share an identical range for Problem Statement — every later
// stage inherits and compounds whichever tier's earlier deadlines applied,
// so both tiers diverge from Evidence Collection onward. End-of-chain totals
// here (critical: day 15, other: day 19) match the source email's own
// "Total days" row.
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

// Shows only the tier that actually applies to this investigation when
// known; both tiers (unlabeled) when the investigation's criticality
// couldn't be determined (2026-08-26, per the user: "it should only show
// applicable definitions for applicable investigations", then "remove the
// text before the colon" — the header names were only needed to tell the
// two figures apart when both showed at once).
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

// Native-tooltip fallback so the full figure is still reachable (on hover)
// for the rare string long enough that the 2-line clamp above ellipsizes it.
function slaTitle(entry: StepSla, tier: "critical" | "other" | null | undefined): string | undefined {
  if (typeof entry === "string") return entry;
  if (tier === "critical") return entry.critical;
  if (tier === "other") return entry.other;
  return `${entry.critical} / ${entry.other}`;
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
  slaTier,
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
  // Which SLA tier applies to this specific investigation (2026-08-26, per
  // the user) — null/undefined shows both tiers (unknown criticality), same
  // as before this was wired up.
  slaTier?: "critical" | "other" | null;
}) {
  const navigate = useNavigate();

  return (
    // paddingBottom reserves room for every step's label+SLA text, which is
    // now absolutely positioned (see below) and so no longer contributes to
    // this row's own layout height — without it, that text would overlap
    // whatever renders directly below the stepper. paddingLeft/Right does
    // the equivalent horizontally for step 1 and step 7 specifically —
    // their label is centered on a circle sitting flush at the row's own
    // edge, so without this buffer its centered (up to 170px wide) text
    // would run off the edge of the page instead of just wrapping
    // (2026-08-26, per the user: "now it's all extending too far").
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
        // Small human-symbol marker between RCI Plan Creation (4) & Task
        // Critique (5), and between Task Critique (5) & RC & CAPA Critique
        // (6) (2026-08-26, per the user) — purely a visual marker on the
        // connecting line, framed by dotted segments on both sides instead
        // of the usual solid line.
        const hasConnectorBox = index === 3 || index === 4;
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
              {/* Absolutely positioned, like the connector's "Manual Input"
                  label — so a long module name or SLA line doesn't widen
                  this step's own box in the row, which was leaving barely
                  any room for the connecting line to the next circle
                  (2026-08-26, per the user: "still not connected"). The
                  row's own height is reserved separately below since this
                  no longer contributes to it. */}
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
                      // Hard-capped at 2 lines regardless of how long the
                      // figure's text is (2026-08-26, per the user) —
                      // ellipsis is the fallback for the rare string that
                      // still wouldn't fit even at this width.
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
            {/* marginTop centers the connector on the 48px step circle
                (circle's own vertical center sits 24px from the top of the
                row, fixed regardless of how many lines of SLA text trail
                below it now that the row top-aligns every step instead of
                centering by each step's own — now variable — total height)
                (2026-08-26, per the user: circles/lines were misaligning
                once some steps' SLA text grew taller than others'). */}
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
