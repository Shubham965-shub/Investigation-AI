import { useEffect, useState } from "react";
import { Outlet, useNavigate, useParams } from "react-router-dom";
import { Stepper, RECORD_STEPS, type StepStatus } from "./Stepper";
import { getProblemStatementRecord } from "../api/dashboard";
import backArrow from "../assets/icons/back-arrow.svg";

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
  const [eventType, setEventType] = useState<string | undefined>(undefined);

  // Only used so the stepper can mark Interview Questionnaire "(Optional)"
  // for Market Complaint investigations — a failed/absent fetch just leaves
  // it unmarked rather than blocking the page.
  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    getProblemStatementRecord(recordId)
      .then((record) => {
        if (!cancelled) setEventType(record?.event_type);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [recordId]);

  if (!recordId) return null;

  return (
    <div style={{ width: "100%", boxSizing: "border-box", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 24 }}>
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
          <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>Investigation AI Assistant</p>
          <p style={{ margin: 0, fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: "var(--font-size-lg)" }}>
            Record Details - Record ID - {recordId}
          </p>
        </div>
      </div>

      <Stepper recordId={recordId} currentStep={currentStep} stepStatuses={deriveStepStatuses(currentStep)} eventType={eventType} />

      <Outlet />
    </div>
  );
}
