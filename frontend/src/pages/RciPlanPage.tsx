import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { generateRciPlan, getProblemStatementRecord, getRciPlanRecord, type RciSectionItem } from "../api/dashboard";
import { ApiError } from "../api/client";
import { getAdditionalFieldsForModule, type EventType, type TrackwiseFields } from "../constants/trackwiseFields";
import { DbErrorModal } from "../components/DbErrorModal";
import rowPlusIcon from "../assets/icons/rci-row-plus.svg";
import rowChevronIcon from "../assets/icons/rci-row-chevron.svg";
import personDefaultIcon from "../assets/icons/rci-person-default.svg";
import exportIcon from "../assets/icons/rci-export-icon.svg";
import documentUploadIcon from "../assets/icons/rci-document-upload.svg";
import penIcon from "../assets/icons/rci-pen-icon.svg";
import "./RecordModulePage.css";

export function RciPlanPage() {
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();

  const [recordLoading, setRecordLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [problemStatement, setProblemStatement] = useState<string | null>(null);
  const [eventType, setEventType] = useState<EventType | undefined>(undefined);
  const [trackwiseFields, setTrackwiseFields] = useState<TrackwiseFields | undefined>(undefined);
  const [sections, setSections] = useState<RciSectionItem[] | null>(null);
  const [openSections, setOpenSections] = useState<Record<number, boolean>>({});
  const [additionalValues, setAdditionalValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Everything comes from the DB — no localStorage. RCI Plan depends on the
  // Problem Statement record existing (fetched here directly rather than
  // assumed from a prior page visit), plus its own record for
  // event_type/trackwise_fields/already-generated plan. A 404 on either is a
  // valid "not generated/no record yet" state; any other failure blocks the
  // page via DbErrorModal.
  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    setRecordLoading(true);
    setDbError(null);
    (async () => {
      try {
        const [psRecord, rciRecord] = await Promise.all([
          getProblemStatementRecord(recordId),
          getRciPlanRecord(recordId),
        ]);
        if (cancelled) return;
        setProblemStatement(psRecord?.problem_statement ?? null);
        if (rciRecord) {
          setEventType(rciRecord.event_type);
          setTrackwiseFields(rciRecord.trackwise_fields);
          if (rciRecord.sections) {
            setSections(rciRecord.sections);
          }
          // The GET response's trackwise_fields already includes the
          // extended field set (Deviation Number, Date Opened, etc.) — pull
          // those straight from the backend instead of leaving the
          // "Additional Details" inputs blank for the user to retype.
          const fieldsNeeded = getAdditionalFieldsForModule("rci-plan", rciRecord.event_type);
          const prefill: Record<string, string> = {};
          for (const field of fieldsNeeded) {
            const value = rciRecord.trackwise_fields[field.key];
            if (typeof value === "string") prefill[field.key] = value;
          }
          setAdditionalValues(prefill);
        }
      } catch (err) {
        if (!cancelled) setDbError(err instanceof ApiError ? String(err.detail) : "Could not reach the database.");
      } finally {
        if (!cancelled) setRecordLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [recordId, retryKey]);

  const additionalFields = useMemo(
    () => (eventType ? getAdditionalFieldsForModule("rci-plan", eventType) : []),
    [eventType]
  );

  if (!recordId) return null;

  if (recordLoading) {
    return (
      <div className="card">
        <p className="card-title">Loading investigation…</p>
      </div>
    );
  }

  if (dbError) {
    return <DbErrorModal message={dbError} onRetry={() => setRetryKey((k) => k + 1)} />;
  }

  if (!problemStatement || !eventType || !trackwiseFields) {
    return (
      <div className="empty-state">
        <p>Complete the Problem Statement step first — RCI Plan needs it to generate a plan.</p>
        <button type="button" className="btn-primary" onClick={() => navigate(`/records/${recordId}/problem-statement`)}>
          Go to Problem Statement
        </button>
      </div>
    );
  }

  async function handleGenerate() {
    setError(null);
    setLoading(true);
    try {
      // DS's schema requires every "list"-kind field (Immediate Actions,
      // Impact Details, Proposal for Resolution) as an actual array, not a
      // string — split each "one per line" text value on newlines. Also
      // make sure every additional field key is present in the payload even
      // if the user never touched it (e.g. "Equipment Number" has no real
      // data source since that DB column was dropped) — DS rejects the
      // request outright if a required key is missing entirely.
      const mergedFields: TrackwiseFields = { ...trackwiseFields };
      for (const field of additionalFields) {
        const raw = additionalValues[field.key] ?? "";
        mergedFields[field.key] =
          field.kind === "list"
            ? raw.split("\n").map((line) => line.trim()).filter(Boolean)
            : raw;
      }
      const response = await generateRciPlan(recordId!, { event_type: eventType!, trackwise_fields: mergedFields });
      // Session-only display — the backend persists this (best-effort) as
      // part of the generate call.
      setSections(response.sections);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Failed to generate RCI plan");
    } finally {
      setLoading(false);
    }
  }

  function toggleSection(index: number) {
    setOpenSections((prev) => ({ ...prev, [index]: !prev[index] }));
  }

  if (!sections) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="card">
          <p className="card-title">Problem Statement</p>
          <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12 }}>
            <p style={{ margin: 0, fontWeight: 600, fontSize: 16, lineHeight: 1.9 }}>{problemStatement}</p>
          </div>
        </div>

        {additionalFields.length > 0 && (
          <div className="card">
            <p className="card-title">Additional Details for RCI Plan</p>
            <p style={{ margin: 0, fontSize: 14, color: "var(--color-text-muted)" }}>
              RCI Plan generation needs a few more details beyond the Problem Statement step.
            </p>
            <div className="field-grid" style={{ flexWrap: "wrap" }}>
              {additionalFields.map((field) => (
                <div key={field.key} style={{ minWidth: 240 }}>
                  <p className="field-label">
                    {field.label}
                    {field.required && " *"}
                  </p>
                  {field.kind === "list" || field.kind === "textarea" ? (
                    <textarea
                      className="field-value"
                      required={field.required}
                      value={additionalValues[field.key] ?? ""}
                      onChange={(e) => setAdditionalValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                    />
                  ) : (
                    <input
                      className="field-value"
                      type={field.kind === "date" ? "date" : field.kind === "time" ? "time" : "text"}
                      required={field.required}
                      value={additionalValues[field.key] ?? ""}
                      onChange={(e) => setAdditionalValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {error && <p className="error-banner">{error}</p>}

        <div className="footer-actions">
          <button type="button" className="btn-primary" onClick={handleGenerate} disabled={loading}>
            {loading ? "Generating…" : "Generate RCI Plan"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card">
        <p className="card-title">Problem Statement</p>
        <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12 }}>
          <p style={{ margin: 0, fontWeight: 600, fontSize: 16, lineHeight: 1.9 }}>{problemStatement}</p>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <p className="card-title">RCI Plan Generated</p>
          <button type="button" className="btn-primary" style={{ display: "flex", alignItems: "center", gap: 10, opacity: 0.5 }} disabled title="Export not wired up yet">
            <img src={exportIcon} alt="" width={16} height={16} />
            Save and Send
          </button>
        </div>
        <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <img src={documentUploadIcon} alt="" width={24} height={24} />
            <div>
              <p style={{ margin: 0, fontWeight: 600, fontSize: 14 }}>RCI Plan.docx</p>
              <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>Not exported yet</p>
            </div>
          </div>
        </div>
      </div>

      <div className="card-header">
        <p className="card-title">RCI Plan</p>
        <button type="button" className="btn-outline" style={{ padding: 8 }} aria-label="Edit" disabled title="Editing not wired up yet">
          <img src={penIcon} alt="" width={16} height={16} />
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {sections.map((section, index) => {
          const isOpen = !!openSections[index];
          return (
            <div key={index} className="card" style={{ gap: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <button type="button" onClick={() => toggleSection(index)} style={{ border: "1px solid var(--color-primary)", borderRadius: 4, width: 34, height: 34, background: "none", display: "flex", alignItems: "center", justifyContent: "center" }} aria-label="Toggle section">
                  <img src={rowPlusIcon} alt="" width={16} height={16} />
                </button>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>
                      {index + 1}. {section.title}
                    </span>
                    <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>({section.tasks.length} tasks)</span>
                  </div>
                  {section.correlation && (
                    <p style={{ margin: "2px 0 0", fontSize: 15, color: "#585858" }}>{section.correlation}</p>
                  )}
                </div>
                <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", fontSize: 16, color: "#585858" }}>
                  TCD: {section.due_date ?? "—"}
                </div>
                <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", display: "flex", alignItems: "center", gap: 8 }}>
                  <img src={personDefaultIcon} alt="" width={16} height={16} />
                  <span style={{ fontSize: 12 }}>{section.assignee ?? "Unassigned"}</span>
                </div>
                <button
                  type="button"
                  onClick={() => toggleSection(index)}
                  style={{ background: "none", border: "none" }}
                  aria-label="Toggle tasks"
                >
                  <img src={rowChevronIcon} alt="" width={24} height={24} style={{ transform: isOpen ? "rotate(0deg)" : "rotate(180deg)" }} />
                </button>
              </div>
              {isOpen && (
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {section.tasks.map((task, taskIndex) => (
                    <li key={taskIndex} style={{ fontSize: 15, color: "var(--color-text)", marginBottom: 4 }}>
                      {task.description}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
