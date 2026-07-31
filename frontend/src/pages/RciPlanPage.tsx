import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  exportRciPlanDocx,
  generateRciPlan,
  getProblemStatementRecord,
  getRciPlanRecord,
  updateRciPlanSections,
  type RciSectionItem,
} from "../api/dashboard";
import { ApiError } from "../api/client";
import { getAdditionalFieldsForModule, nativeInputType, type EventType, type TrackwiseFields } from "../constants/trackwiseFields";
import { DbErrorModal } from "../components/DbErrorModal";
import { ConfirmDialog } from "../components/ConfirmDialog";
import rowPlusIcon from "../assets/icons/rci-row-plus.svg";
import rowChevronIcon from "../assets/icons/rci-row-chevron.svg";
import personDefaultIcon from "../assets/icons/rci-person-default.svg";
import exportIcon from "../assets/icons/rci-export-icon.svg";
import penIcon from "../assets/icons/rci-pen-icon.svg";
import checkIcon from "../assets/icons/evidence-checkbox.svg";
import "./RecordModulePage.css";

// TCD (target completion date) must be a future date — per the user
// (2026-07-31), the calendar picker should only allow dates after today, so
// this is used as the <input type="date">'s min (exclusive of today itself).
function tomorrowIso(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

export function RciPlanPage() {
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();
  const persistTimerRef = useRef<number | null>(null);
  const minDueDate = useMemo(() => tomorrowIso(), []);

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
  const [showConfirm, setShowConfirm] = useState(false);
  const [pushed, setPushed] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

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
            // "list"-kind fields (Immediate Actions, Impact Details, Proposal
            // for Resolution) come back as arrays — join with "\n" to match
            // the same one-per-line textarea convention handleGenerate's
            // split("\n") expects on submit, instead of dropping the field
            // (typeof value === "string" alone would silently leave it
            // blank, same class of bug as Related Market/Related Customer).
            if (typeof value === "string") prefill[field.key] = value;
            else if (Array.isArray(value)) prefill[field.key] = value.join("\n");
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

  // Persisted best-effort, debounced 600ms after the last edit — typing in
  // the investigator field fired a full replace-all-sections PUT on every
  // keystroke, which (combined with a since-fixed backend race — see
  // replace_rci_sections) produced duplicated sections with different
  // partially-typed substrings of "Unassigned" as the assignee. The backend
  // fix alone prevents the corruption; debouncing here also cuts the sheer
  // number of full-replace round-trips a fast typist fires.
  function persistSections(list: RciSectionItem[]) {
    if (!recordId) return;
    if (persistTimerRef.current) window.clearTimeout(persistTimerRef.current);
    persistTimerRef.current = window.setTimeout(() => {
      updateRciPlanSections(recordId, list).catch((err) => {
        console.error("Failed to persist RCI plan sections", err);
      });
    }, 600);
  }

  function setSectionAssignee(index: number, assignee: string) {
    if (!sections) return;
    const newSections = sections.map((s, i) => (i === index ? { ...s, assignee } : s));
    setSections(newSections);
    persistSections(newSections);
  }

  function setSectionDueDate(index: number, dueDate: string) {
    if (!sections) return;
    const newSections = sections.map((s, i) => (i === index ? { ...s, due_date: dueDate || null } : s));
    setSections(newSections);
    persistSections(newSections);
  }

  // Real .docx download — the backend fills the company's actual RCI Plan
  // Word template (assets/rci_plan_template.docx) with this investigation's
  // persisted sections and returns the file directly.
  async function downloadRciPlanDocument() {
    if (!recordId) return;
    const blob = await exportRciPlanDocx(recordId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `RCI_Plan_${recordId}.docx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function handleAcceptAndPush() {
    setShowConfirm(false);
    setExportError(null);
    try {
      await downloadRciPlanDocument();
      setPushed(true);
      setTimeout(() => setPushed(false), 1500);
    } catch (err) {
      setExportError(err instanceof ApiError ? String(err.detail) : "Failed to export the RCI plan document");
    }
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
                      type={nativeInputType(field.kind, additionalValues[field.key] ?? "")}
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
                <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", display: "flex", alignItems: "center", gap: 6, fontSize: 16, color: "#585858" }}>
                  <span>TCD:</span>
                  <input
                    type="date"
                    min={minDueDate}
                    value={section.due_date ?? ""}
                    onChange={(e) => setSectionDueDate(index, e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    style={{ border: "none", background: "none", fontSize: 16, color: "#585858", padding: 0 }}
                  />
                </div>
                <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", display: "flex", alignItems: "center", gap: 8 }}>
                  <img src={personDefaultIcon} alt="" width={16} height={16} />
                  <input
                    type="text"
                    placeholder="Unassigned"
                    value={section.assignee ?? ""}
                    onChange={(e) => setSectionAssignee(index, e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    style={{ fontSize: 12, border: "none", background: "none", width: 90, padding: 0 }}
                  />
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
                <div style={{ border: "1px solid var(--color-card-border)", borderRadius: 4, overflow: "hidden" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", background: "var(--color-bg)", borderBottom: "1px solid var(--color-card-border)", padding: "8px 16px", fontSize: 12, fontWeight: 600, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: 0.3 }}>
                    <span style={{ width: 700 }}>Task</span>
                    <span style={{ width: 160 }}>Description</span>
                    <span style={{ width: 160 }}>Assigned To</span>
                  </div>
                  {section.tasks.map((task, taskIndex) => (
                    <div
                      key={taskIndex}
                      style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 16px", borderBottom: taskIndex < section.tasks.length - 1 ? "1px solid var(--color-card-border)" : "none" }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 10, width: 700 }}>
                        <span style={{ background: "var(--color-primary)", border: "2px solid var(--color-primary)", borderRadius: 4, width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                          <img src={checkIcon} alt="" width={12} height={12} />
                        </span>
                        <span style={{ fontSize: 14, fontWeight: 600, color: "#374151" }}>{task.description}</span>
                      </div>
                      <span style={{ fontSize: 14, color: "#374151", width: 160 }}>Description goes here...</span>
                      <span style={{ fontSize: 14, color: "#374151", width: 160 }}>{section.assignee ?? "Unassigned"}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {exportError && <p className="error-banner">{exportError}</p>}

      <div className="footer-actions">
        <button type="button" className="btn-primary" style={{ display: "flex", alignItems: "center", gap: 10 }} onClick={() => setShowConfirm(true)}>
          <img src={exportIcon} alt="" width={16} height={16} />
          {pushed ? "Pushed — downloading…" : "Accept and Push to TW"}
        </button>
      </div>

      {showConfirm && (
        <ConfirmDialog
          title="Accept RCI Plan?"
          message="Are you sure you want to accept the RCI Plan and push it to Trackwise? The generated document will be downloaded to your device."
          onCancel={() => setShowConfirm(false)}
          onConfirm={handleAcceptAndPush}
        />
      )}
    </div>
  );
}
