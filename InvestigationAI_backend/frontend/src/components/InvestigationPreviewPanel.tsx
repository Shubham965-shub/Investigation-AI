import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { usePanelState } from "./PanelStateContext";
import backArrow from "../assets/icons/panel-back-arrow.svg";
import closeIcon from "../assets/icons/panel-close.png";
import calendarIcon from "../assets/icons/panel-calendar.svg";
import teamIcon from "../assets/icons/panel-team.svg";
import inProgressBannerIcon from "../assets/icons/panel-inprogress-banner.svg";
import jumpArrowIcon from "../assets/icons/panel-jump-arrow.svg";
import stepCompletedIcon from "../assets/icons/panel-step-completed.svg";
import badgeCompletedIcon from "../assets/icons/panel-badge-completed.svg";
import stepInProgressIcon from "../assets/icons/panel-step-inprogress.svg";
import badgeInProgressIcon from "../assets/icons/panel-badge-inprogress.svg";
import stepNotStartedIcon from "../assets/icons/panel-step-notstarted.svg";
import badgeNotStartedIcon from "../assets/icons/panel-badge-notstarted.svg";
import unassignedIcon from "../assets/icons/panel-unassigned.svg";

// Matches the approved Figma "Action Center_right_Sheet" panel (node 1229:39035 / 1229:39560).
// Step descriptions/labels are still fabricated from that design's sample
// content (no backend for per-step metadata yet). The investigation
// team/assignee display, however, uses the real investigator actually
// assigned to this investigation (investigation.investigator, sourced from
// GET /action-center/summary) — no more hardcoded team roster.

// Matches AppHeader's rendered height so the panel/backdrop never covers
// the persistent Strides/Athena header.
const HEADER_HEIGHT = 83;

export interface PreviewInvestigation {
  id: string;
  title: string;
  eventType: string;
  investigator: string;
  step: number;
  totalSteps: number;
  dueDate: string;
}

function initialsFor(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

const STEP_DEFS: { label: string; description: string; path: string | null }[] = [
  { label: "Problem Statement Generation", description: "Generate the problem statement for the investigation.", path: "problem-statement" },
  { label: "Evidence Collection", description: "List of Evidences to be collected for the investigation.", path: "evidence-collection" },
  { label: "Interview Questionnaire", description: "Creation of interview Questionnaire.", path: "interview-questionnaire" },
  { label: "RCI Plan Creation", description: "RCI plan creation based on the Collected evidence and Interview questionnaire's response.", path: "rci-plan" },
  { label: "Task Critique", description: "Critique the tasks that is completed by the RCI plan creation step.", path: null },
  { label: "RC & CAPA Critique", description: "Final report generation of the investigation.", path: null },
  { label: "RCI Report", description: "Final quality review and investigation closure with the reviews.", path: null },
];

export function InvestigationPreviewPanel({
  investigation,
  onClose,
}: {
  investigation: PreviewInvestigation | null;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const isOpen = investigation !== null;
  const { setPanelOpen } = usePanelState();

  useEffect(() => {
    setPanelOpen(isOpen);
    return () => setPanelOpen(false);
  }, [isOpen, setPanelOpen]);

  useEffect(() => {
    if (!isOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  const percent = investigation ? Math.round((investigation.step / investigation.totalSteps) * 100) : 0;
  const currentStepDef = investigation ? STEP_DEFS[investigation.step] : undefined;

  function goToStep(path: string | null) {
    if (!investigation || !path) return;
    navigate(`/records/${investigation.id}/${path}`);
  }

  return (
    <>
      <div
        onClick={onClose}
        style={{
          // Covers the full viewport, including the header's own strip —
          // the header's z-index (70) still paints over it once settled, so
          // it never looks dimmed; this just avoids a plain white gap behind
          // the header while it's still sliding down into place.
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: "rgba(15, 23, 42, 0.35)",
          opacity: isOpen ? 1 : 0,
          pointerEvents: isOpen ? "auto" : "none",
          transition: "opacity 200ms ease",
          zIndex: 40,
        }}
      />
      <div
        role="dialog"
        aria-hidden={!isOpen}
        style={{
          position: "fixed",
          top: HEADER_HEIGHT,
          right: 0,
          height: `calc(100% - ${HEADER_HEIGHT}px)`,
          width: "min(892px, 92vw)",
          background: "var(--color-bg)",
          boxShadow: "0 25px 25px rgba(0,0,0,0.25)",
          transform: isOpen ? "translateX(0)" : "translateX(100%)",
          transition: "transform 250ms ease",
          zIndex: 50,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {investigation && currentStepDef && (
          <>
            <div style={{ background: "var(--color-surface)", borderBottom: "1px solid var(--color-card-border)", padding: "16px 16px 17px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexShrink: 0 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <button type="button" aria-label="Close" onClick={onClose} style={{ background: "none", border: "none", padding: 0, display: "flex", cursor: "pointer" }}>
                    <img src={backArrow} alt="" width={14} height={14} />
                  </button>
                  <span style={{ fontFamily: "monospace", fontSize: 14, color: "#444746" }}>{investigation.id}</span>
                  <span style={{ color: "var(--color-text-muted)" }}>/</span>
                  <span style={{ fontFamily: "monospace", fontSize: 14, color: "#444746" }}>{investigation.eventType}</span>
                </div>
                <p style={{ margin: 0, fontWeight: 700, fontSize: 20, color: "var(--color-text)" }}>{investigation.title}</p>
              </div>
              <button type="button" aria-label="Close panel" onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", padding: 5 }}>
                <img src={closeIcon} alt="" width={18} height={18} />
              </button>
            </div>

            <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ background: "var(--color-rail-active-bg)", borderBottom: "1px solid var(--color-card-border)", padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
                <p style={{ margin: 0, fontSize: 14, fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
                  Investigation Summary
                </p>
                <div style={{ display: "flex", gap: 12 }}>
                  <div style={{ flex: 1, background: "var(--color-surface)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                    <p style={{ margin: 0, fontWeight: 600, fontSize: 14 }}>Overall Progress</p>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                      <span style={{ fontSize: 20, fontWeight: 700 }}>{percent}%</span>
                      <span style={{ fontSize: 14, color: "var(--color-text-muted)" }}>
                        {investigation.step} of {investigation.totalSteps} steps complete
                      </span>
                    </div>
                    <div style={{ height: 5, borderRadius: 99, background: "var(--color-open-bg)", overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${percent}%`, borderRadius: 99, background: "#00bc7d" }} />
                    </div>
                  </div>
                  <div style={{ flex: 1, background: "var(--color-surface)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12, display: "flex", justifyContent: "space-between" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <img src={calendarIcon} alt="" width={14} height={14} />
                      <p style={{ margin: 0, fontWeight: 600, fontSize: 14 }}>Due Date</p>
                      <p style={{ margin: 0, fontSize: 16 }}>{investigation.dueDate}</p>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <img src={calendarIcon} alt="" width={14} height={14} />
                      <p style={{ margin: 0, fontWeight: 600, fontSize: 14 }}>Last Updated</p>
                      <p style={{ margin: 0, fontSize: 16 }}>{investigation.dueDate}</p>
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <img src={teamIcon} alt="" width={16} height={16} />
                    <p style={{ margin: 0, fontWeight: 600, fontSize: 14 }}>Investigation Team</p>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {investigation.investigator ? (
                      <div style={{ background: "var(--color-rail-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "5px 9px", display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ background: "#4a5565", color: "#fff", borderRadius: "50%", width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 8, fontWeight: 700 }}>
                          {initialsFor(investigation.investigator)}
                        </span>
                        <div>
                          <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: "var(--color-text)" }}>{investigation.investigator}</p>
                          <p style={{ margin: 0, fontSize: 10, color: "var(--color-text-muted)" }}>Investigator</p>
                        </div>
                      </div>
                    ) : (
                      <p style={{ margin: 0, fontSize: 13, color: "var(--color-text-muted)" }}>Unassigned</p>
                    )}
                  </div>
                </div>
              </div>

              {currentStepDef.path && (
                <div style={{ padding: "0 16px" }}>
                  <div style={{ background: "#eff6ff", border: "1px solid #2b7fff", borderRadius: 4, padding: "11.5px 15px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                      <img src={inProgressBannerIcon} alt="" width={14} height={14} />
                      <div>
                        <p style={{ margin: 0, fontSize: "10.5px", fontWeight: 600, color: "#2b7fff" }}>Currently in progress</p>
                        <p style={{ margin: 0, fontSize: 11, color: "#2b7fff" }}>
                          Step {investigation.step + 1}: {currentStepDef.label}
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => goToStep(currentStepDef.path)}
                      style={{ background: "#dce2eb", border: "none", borderRadius: 4, padding: "5px 11px", display: "flex", alignItems: "center", gap: 4, color: "#2b7fff", fontSize: "10.5px", fontWeight: 600 }}
                    >
                      Jump to step
                      <img src={jumpArrowIcon} alt="" width={10} height={10} />
                    </button>
                  </div>
                </div>
              )}

              <div style={{ padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 16 }}>
                <p style={{ margin: 0, fontSize: 14, fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
                  Investigation Steps
                </p>
                {STEP_DEFS.map((stepDef, index) => {
                  const status = index < investigation.step ? "completed" : index === investigation.step ? "in-progress" : "not-started";
                  const isLast = index === STEP_DEFS.length - 1;
                  const circleIcon = status === "completed" ? stepCompletedIcon : status === "in-progress" ? stepInProgressIcon : stepNotStartedIcon;
                  const circleStyle =
                    status === "completed"
                      ? { background: "#ecfdf5", border: "2px solid #00d492" }
                      : status === "in-progress"
                      ? { background: "#fffbeb", border: "2px solid #ffb900" }
                      : { background: "var(--color-open-bg)", border: "2px solid var(--color-card-border)" };
                  const cardBorder = status === "completed" ? "#028662" : status === "in-progress" ? "#fe9a00" : "var(--color-open-bg)";

                  return (
                    <div key={stepDef.label} style={{ display: "flex", gap: 14, opacity: status === "not-started" ? 0.6 : 1 }}>
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3.5, alignSelf: "stretch", width: 28, flexShrink: 0 }}>
                        <div style={{ width: 28, height: 28, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, ...circleStyle }}>
                          <img src={circleIcon} alt="" width={14} height={14} />
                        </div>
                        {!isLast && <div style={{ flex: 1, width: 1.75, background: status === "completed" ? "#00d492" : "var(--color-card-border)", opacity: status === "completed" ? 0.4 : 1 }} />}
                      </div>
                      <div style={{ flex: 1, minWidth: 0, paddingBottom: 16 }}>
                        <div
                          onClick={stepDef.path ? () => goToStep(stepDef.path) : undefined}
                          role={stepDef.path ? "button" : undefined}
                          tabIndex={stepDef.path ? 0 : undefined}
                          onKeyDown={stepDef.path ? (e) => (e.key === "Enter" || e.key === " ") && goToStep(stepDef.path) : undefined}
                          style={{
                            background: "var(--color-surface)",
                            border: `1px solid ${cardBorder}`,
                            borderRadius: 8,
                            padding: 15,
                            display: "flex",
                            flexDirection: "column",
                            gap: 12,
                            cursor: stepDef.path ? "pointer" : "default",
                          }}
                        >
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 4,
                              alignSelf: "flex-start",
                              padding: "8px",
                              borderRadius: 4,
                              fontSize: 12,
                              fontWeight: 600,
                              ...(status === "completed"
                                ? { background: "#f0fdfa", border: "1px solid #00786f", color: "#00786f" }
                                : status === "in-progress"
                                ? { background: "#fffbeb", border: "1px solid #fe9a00", color: "#fe9a00" }
                                : { background: "#e6e6e6", border: "1px solid #4d4d4d", color: "#4d4d4d" }),
                            }}
                          >
                            <img src={status === "completed" ? badgeCompletedIcon : status === "in-progress" ? badgeInProgressIcon : badgeNotStartedIcon} alt="" width={16} height={16} />
                            {status === "completed" ? "Completed" : status === "in-progress" ? "In Progress" : "Not Started"}
                          </span>
                          <p style={{ margin: 0, fontWeight: 600, fontSize: 16, color: "var(--color-text)" }}>{stepDef.label}</p>
                          <p style={{ margin: 0, fontSize: 14, color: "var(--color-text-muted)" }}>{stepDef.description}</p>
                          <div style={{ borderTop: "1px solid var(--color-card-border)", paddingTop: 8, width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                            {status !== "not-started" && investigation.investigator ? (
                              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <span style={{ background: "#4a5565", color: "#fff", borderRadius: "50%", width: 24, height: 24, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700 }}>
                                  {initialsFor(investigation.investigator)}
                                </span>
                                <div>
                                  <p style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "var(--color-text)" }}>{investigation.investigator}</p>
                                  <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>Investigator</p>
                                </div>
                              </div>
                            ) : (
                              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <span style={{ width: 30, height: 30, borderRadius: "50%", border: "1.4px dashed var(--color-open-border)", background: "var(--color-open-bg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                                  <img src={unassignedIcon} alt="" width={15} height={15} />
                                </span>
                                <span style={{ fontSize: 14, fontWeight: 700, color: "var(--color-text)" }}>Unassigned</span>
                              </div>
                            )}
                            {status === "in-progress" && stepDef.path && (
                              <button type="button" onClick={() => goToStep(stepDef.path)} style={{ background: "var(--color-primary)", color: "#fff", border: "none", borderRadius: 4, padding: "4px 16px", fontSize: 14, fontWeight: 700 }}>
                                Continue
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
