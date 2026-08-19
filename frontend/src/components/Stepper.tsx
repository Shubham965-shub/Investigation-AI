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
  { key: "rc-capa-critique", label: "RC & CAPA Critique", path: "rc-capa-critique" },
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
            {!isLast && (
              <div
                style={{
                  height: 2,
                  flex: 1,
                  margin: "0 8px 24px",
                  background: status === "completed" ? "var(--color-primary)" : "var(--color-open-border)",
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
