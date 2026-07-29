import { Outlet, useNavigate, useParams } from "react-router-dom";
import { Stepper, RECORD_STEPS, type StepStatus } from "./Stepper";
import backArrow from "../assets/icons/back-arrow.svg";
import bookmark from "../assets/icons/bookmark.svg";

// Placeholder record label + step-status derivation until a real "fetch
// record by id" endpoint exists (see project memory: landing/list-investigations gap).
function deriveStepStatuses(currentStep: string): Record<string, StepStatus> {
  const currentIndex = RECORD_STEPS.findIndex((s) => s.key === currentStep);
  const statuses: Record<string, StepStatus> = {};
  RECORD_STEPS.forEach((step, index) => {
    if (index < currentIndex) statuses[step.key] = "completed";
    else if (index === currentIndex) statuses[step.key] = "in-progress";
    else statuses[step.key] = "open";
  });
  return statuses;
}

export function RecordShell({ currentStep }: { currentStep: string }) {
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();
  if (!recordId) return null;

  return (
    <div style={{ width: "100%", boxSizing: "border-box", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <button
            type="button"
            aria-label="Back"
            onClick={() => navigate("/")}
            style={{ background: "none", border: "none", padding: 0, display: "flex", cursor: "pointer" }}
          >
            <img src={backArrow} alt="" width={20} height={20} />
          </button>
          <div>
            <p style={{ margin: 0, fontSize: 14, color: "var(--color-text-muted)" }}>Investigation AI Assistant</p>
            <p style={{ margin: 0, fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: 20 }}>
              Record Details - REC - {recordId}
            </p>
          </div>
        </div>
        <button
          type="button"
          style={{
            background: "var(--color-primary)",
            border: "1px solid var(--color-primary)",
            borderRadius: "var(--radius-btn)",
            color: "#fafafa",
            fontFamily: "var(--font-heading)",
            fontWeight: 700,
            padding: "8px 16px",
            opacity: 0.4,
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
          disabled
        >
          <img src={bookmark} alt="" width={24} height={24} />
          Check IQ Rubrics
        </button>
      </div>

      <Stepper recordId={recordId} currentStep={currentStep} stepStatuses={deriveStepStatuses(currentStep)} />

      <Outlet />
    </div>
  );
}
