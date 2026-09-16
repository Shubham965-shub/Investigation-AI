import { useEffect, useState, type CSSProperties } from "react";
import { Outlet, useNavigate, useParams } from "react-router-dom";
import { Stepper, RECORD_STEPS, type StepStatus } from "./Stepper";
import { getProblemStatementRecord } from "../api/dashboard";
import backArrow from "../assets/icons/back-arrow.svg";

// Placeholder step-status derivation until a real "fetch record by id" endpoint exists.
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
  const [criticality, setCriticality] = useState<string | null | undefined>(undefined);
  const [eventClassification, setEventClassification] = useState<string | null | undefined>(undefined);

  // A failed/absent fetch just leaves eventType/criticality unmarked rather than blocking the page.
  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    getProblemStatementRecord(recordId)
      .then((record) => {
        if (!cancelled) {
          setEventType(record?.event_type);
          setCriticality(record?.criticality ?? null);
          setEventClassification(record?.event_classification ?? null);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [recordId]);

  // OOS/OOT always gets the strict tier (no data distinguishes stability/microbiocidal failures from others, so err strict). Deviation/Market Complaint: anything other than exactly "Critical" (including null/missing) defaults to "other".
  const slaTier: "critical" | "other" =
    eventType === "OOS" || eventType === "OOT" || eventType === "OOS/OOT" || criticality === "Critical"
      ? "critical"
      : "other";

  if (!recordId) return null;

  // "Critical" reuses Action Center's Critical badge style; Major/Minor get a plain grey tag; anything else shows nothing.
  const classificationTagStyle: CSSProperties | null =
    eventClassification === "Critical"
      ? { border: "1px solid var(--color-danger-text)", color: "var(--color-danger-text)" }
      : eventClassification === "Major" || eventClassification === "Minor"
      ? { background: "var(--color-open-bg)", color: "var(--color-text-muted)" }
      : null;

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
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <p style={{ margin: 0, fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: "var(--font-size-lg)" }}>
              Record Details - Record ID - {recordId}
            </p>
            {classificationTagStyle && (
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  borderRadius: "var(--radius-btn)",
                  padding: "3px 10px",
                  fontSize: "var(--font-size-sm)",
                  fontWeight: 600,
                  ...classificationTagStyle,
                }}
              >
                {eventClassification}
              </span>
            )}
          </div>
        </div>
      </div>

      <Stepper recordId={recordId} currentStep={currentStep} stepStatuses={deriveStepStatuses(currentStep)} eventType={eventType} slaTier={slaTier} />

      <Outlet />
    </div>
  );
}
