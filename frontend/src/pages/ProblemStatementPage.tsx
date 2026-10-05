import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  EVENT_TYPE_OPTIONS,
  getFieldSet,
  nativeInputType,
  type EventType,
  type TrackwiseFields,
} from "../constants/trackwiseFields";
import {
  generateProblemStatement,
  generateProblemStatementEnhancements,
  getProblemStatementRecord,
  updateProblemStatement,
  type ProblemStatementEnhancement,
} from "../api/dashboard";
import { ApiError } from "../api/client";
import { DbErrorModal } from "../components/DbErrorModal";
import { GeneratingDialog } from "../components/GeneratingDialog";
import { ProblemStatementGuidelines } from "../components/ProblemStatementGuidelines";
import { recordPath, fromRciSegment } from "../lib/rci";
import { track, EVENTS } from "../telemetry/events";
import copyIcon from "../assets/icons/copy-icon.svg";
import chevronEntry from "../assets/icons/chevron-entry.svg";
import "./RecordModulePage.css";

function groupBySection(fields: ReturnType<typeof getFieldSet>) {
  const groups = new Map<string, typeof fields>();
  for (const field of fields) {
    const section = field.section ?? "Details";
    if (!groups.has(section)) groups.set(section, []);
    groups.get(section)!.push(field);
  }
  return Array.from(groups.entries());
}

export function ProblemStatementPage() {
  const { recordId, rciId } = useParams<{ recordId: string; rciId: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [eventType, setEventType] = useState<EventType>(EVENT_TYPE_OPTIONS["problem-statement"][0]);
  // True once a real DB record exists — trackwise_fields is already real data then, so the entry form switches to read-only.
  const [recordExists, setRecordExists] = useState(false);
  // True once Evidence Collection has any real data — hides the "Edit Problem Statement" option.
  const [lockedForEditing, setLockedForEditing] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [problemStatement, setProblemStatement] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Shown while a saved edit's PUT is in flight.
  const [savingEdit, setSavingEdit] = useState(false);
  const [copied, setCopied] = useState(false);
  // The generated problem statement is editable inline at all times (while unlocked) — draftPs
  // tracks the textarea's live value; nothing is persisted until "Save Problem Statement" is clicked.
  const [draftPs, setDraftPs] = useState("");
  // Defaults open to match the reference layout — all TrackWise sections visible on first view.
  const [viewAllOpen, setViewAllOpen] = useState(true);
  // null = never generated yet; [] = generated, nothing meaningful found; undefined briefly while the record itself is still loading.
  // Still fetched/persisted below (loadEnhancements, the load effect, handleSaveAndNext) even
  // though the "What Was Enhanced" display is commented out — kept ready for when it's restored.
  const [enhancements, setEnhancements] = useState<ProblemStatementEnhancement[] | null>(null);
  const [enhancementsLoading, setEnhancementsLoading] = useState(false);
  const [enhancementsError, setEnhancementsError] = useState<string | null>(null);
  void enhancements;
  void enhancementsLoading;
  void enhancementsError;
  // Only used by the commented-out "What Was Enhanced" UI's collapse toggle below.
  // const [enhancementsOpen, setEnhancementsOpen] = useState(true);

  function loadEnhancements() {
    setEnhancementsError(null);
    setEnhancementsLoading(true);
    generateProblemStatementEnhancements(rid, normalizedRciId)
      .then((res) => setEnhancements(res.enhancements))
      .catch((err) => setEnhancementsError(err instanceof ApiError ? String(err.detail) : "Failed to analyze changes"))
      .finally(() => setEnhancementsLoading(false));
  }

  // A 404 (no record yet) is a valid, non-error state; any other failure blocks the page via DbErrorModal.
  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    setLoading(true);
    setDbError(null);
    (async () => {
      try {
        const record = await getProblemStatementRecord(recordId, fromRciSegment(rciId) || null);
        if (cancelled) return;
        if (record) {
          setRecordExists(true);
          setEventType(record.event_type);
          const initialValues: Record<string, string> = {};
          for (const [k, v] of Object.entries(record.trackwise_fields)) {
            if (typeof v === "string") initialValues[k] = v;
          }
          setValues(initialValues);
          setProblemStatement(record.problem_statement);
          setDraftPs(record.problem_statement ?? "");
          setLockedForEditing(record.locked_for_editing ?? false);
          setEnhancements(record.enhancements ?? null);
        }
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        setDbError(err instanceof ApiError ? String(err.detail) : "Could not reach the database.");
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [recordId, rciId, retryKey]);

  const fields = useMemo(() => getFieldSet("problem-statement", eventType), [eventType]);
  const sections = useMemo(() => groupBySection(fields), [fields]);

  if (!recordId) return null;
  const rid: string = recordId;
  const normalizedRciId = fromRciSegment(rciId) || null;

  if (loading) {
    return (
      <div className="card">
        <p className="card-title">Loading investigation…</p>
      </div>
    );
  }

  if (dbError) {
    return <DbErrorModal message={dbError} onRetry={() => setRetryKey((k) => k + 1)} />;
  }

  function handleFieldChange(key: string, value: string) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function toggleSection(section: string) {
    setCollapsed((prev) => ({ ...prev, [section]: !prev[section] }));
  }

  async function handleGenerate() {
    setError(null);
    const trackwiseFields: TrackwiseFields = {};
    for (const field of fields) {
      trackwiseFields[field.key] = values[field.key] ?? "";
    }

    setSubmitting(true);
    try {
      const response = await generateProblemStatement(rid, normalizedRciId, { event_type: eventType, trackwise_fields: trackwiseFields });
      // Session-only display — the backend already persists this (best-effort) as part of the generate call.
      setProblemStatement(response.problem_statement);
      setDraftPs(response.problem_statement);
      track(EVENTS.problemStatementGenerated, { recordId: rid, rciId: normalizedRciId });
      // Fire-and-forget: the "What Was Enhanced" panel populates itself once this resolves — a
      // slow/failed enhancements call must not block the primary problem-statement flow.
      loadEnhancements();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Failed to generate problem statement");
    } finally {
      setSubmitting(false);
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(draftPs).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  // The single confirm action: persists any edit made to the generated text (skipped if nothing
  // changed, or if the record is locked once Evidence Collection has started), then advances.
  function handleSaveAndNext() {
    if (lockedForEditing || draftPs === problemStatement) {
      navigate(recordPath(rid, normalizedRciId, "evidence-collection"));
      return;
    }
    setError(null);
    setSavingEdit(true);
    updateProblemStatement(rid, normalizedRciId, draftPs)
      .then(() => {
        setProblemStatement(draftPs);
        // The backend clears the persisted diff on edit too — it was computed against the pre-edit text.
        setEnhancements(null);
        track(EVENTS.problemStatementEdited, { recordId: rid, rciId: normalizedRciId });
        navigate(recordPath(rid, normalizedRciId, "evidence-collection"));
      })
      .catch((err) => {
        setError(err instanceof ApiError ? String(err.detail) : "Failed to save the problem statement");
      })
      .finally(() => setSavingEdit(false));
  }

  if (problemStatement) {
    return (
      <>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* TW Details / LLM Enhanced Details side-by-side comparison — commented out, UI only.
        <div className="field-grid" style={{ alignItems: "stretch" }}>
          <div className="card">
            <div className="card-header">
              <p className="card-title">TW Details</p>
              <span className="status-pill source">Source</span>
            </div>
            <div style={{ background: "var(--color-bg)", borderRadius: 4, padding: 12 }}>
              <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-lg)", lineHeight: 1.8 }}>
                {values.description || "—"}
              </p>
            </div>
          </div>

          <div className="card" style={{ borderColor: "var(--color-success-border)" }}>
            <div className="card-header">
              <p className="card-title">LLM Enhanced Details <ProblemStatementGuidelines /></p>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="status-pill ai-generated">AI Generated</span>
                <button type="button" className="btn-outline" onClick={handleCopy}>
                  <img src={copyIcon} alt="" width={18} height={18} />
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
            </div>
            {lockedForEditing ? (
              <div style={{ background: "var(--color-success-bg)", borderRadius: 4, padding: 12, border: "1px solid var(--color-success-border)" }}>
                <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-lg)", lineHeight: 1.8 }}>{problemStatement}</p>
              </div>
            ) : (
              <textarea
                className="field-value"
                value={draftPs}
                onChange={(e) => setDraftPs(e.target.value)}
                rows={5}
                style={{
                  background: "var(--color-success-bg)",
                  borderColor: "var(--color-success-border)",
                  fontWeight: 600,
                  fontSize: "var(--font-size-lg)",
                  lineHeight: 1.6,
                }}
              />
            )}
          </div>
        </div>
        */}

        {/* Generated Problem Statement — single card, no TW comparison. */}
        <div className="card" style={{ borderColor: "var(--color-success-border)" }}>
          <div className="card-header">
            <p className="card-title">Problem Statement <ProblemStatementGuidelines /></p>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="status-pill ai-generated">AI Generated</span>
              <button type="button" className="btn-outline" onClick={handleCopy}>
                <img src={copyIcon} alt="" width={18} height={18} />
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </div>
          {lockedForEditing ? (
            <div style={{ background: "var(--color-success-bg)", borderRadius: 4, padding: 12, border: "1px solid var(--color-success-border)" }}>
              <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-lg)", lineHeight: 1.8 }}>{problemStatement}</p>
            </div>
          ) : (
            <textarea
              className="field-value"
              value={draftPs}
              onChange={(e) => setDraftPs(e.target.value)}
              rows={5}
              style={{
                background: "var(--color-success-bg)",
                borderColor: "var(--color-success-border)",
                fontWeight: 600,
                fontSize: "var(--font-size-lg)",
                lineHeight: 1.6,
              }}
            />
          )}
        </div>

        <div className="card">
          <div className="card-header">
            <p className="card-title">View All Details</p>
            <button
              type="button"
              className="collapse-chevron"
              onClick={() => setViewAllOpen((prev) => !prev)}
              style={{ background: "none", border: "none", cursor: "pointer" }}
              aria-label="Toggle View All Details"
            >
              <img
                src={chevronEntry}
                alt=""
                width={20}
                height={20}
                style={{ transform: viewAllOpen ? "rotate(90deg)" : "rotate(-90deg)" }}
              />
            </button>
          </div>
          {viewAllOpen && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {sections.map(([section, sectionFields]) => (
                <div key={section} style={{ border: "1px solid var(--color-card-border)", borderRadius: 8, padding: 16 }}>
                  <div className="card-header">
                    <p className="card-title" style={{ fontSize: "var(--font-size-md)" }}>{section}</p>
                    <button
                      type="button"
                      className="collapse-chevron"
                      onClick={() => toggleSection(section)}
                      style={{ background: "none", border: "none", cursor: "pointer" }}
                      aria-label={`Toggle ${section}`}
                    >
                      <img
                        src={chevronEntry}
                        alt=""
                        width={20}
                        height={20}
                        style={{ transform: collapsed[section] ? "rotate(90deg)" : "rotate(-90deg)" }}
                      />
                    </button>
                  </div>
                  {!collapsed[section] && (
                    <div className="field-grid" style={{ flexWrap: "wrap" }}>
                      {sectionFields.map((field) => (
                        <div key={field.key} style={{ minWidth: 240 }}>
                          <p className="field-label">{field.label}</p>
                          <div className="field-value">{values[field.key] || "—"}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* "What Was Enhanced" panel — commented out, UI only.
        <div className="card">
          <div className="card-header">
            <p className="card-title">What Was Enhanced</p>
            <button
              type="button"
              className="collapse-chevron"
              onClick={() => setEnhancementsOpen((prev) => !prev)}
              style={{ background: "none", border: "none", cursor: "pointer" }}
              aria-label="Toggle What Was Enhanced"
            >
              <img
                src={chevronEntry}
                alt=""
                width={20}
                height={20}
                style={{ transform: enhancementsOpen ? "rotate(90deg)" : "rotate(-90deg)" }}
              />
            </button>
          </div>
          {enhancementsOpen && (
            <>
              {enhancementsLoading && (
                <p style={{ margin: 0, color: "var(--color-text-muted)" }}>Analyzing what changed…</p>
              )}
              {!enhancementsLoading && enhancementsError && (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                  <p style={{ margin: 0, color: "var(--color-danger-text)" }}>{enhancementsError}</p>
                  <button type="button" className="btn-outline" onClick={loadEnhancements}>
                    Retry
                  </button>
                </div>
              )}
              {!enhancementsLoading && !enhancementsError && enhancements === null && (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                  <p style={{ margin: 0, color: "var(--color-text-muted)" }}>
                    Not yet analyzed — compares the raw TrackWise text against the generated problem statement.
                  </p>
                  <button type="button" className="btn-outline" onClick={loadEnhancements}>
                    Generate
                  </button>
                </div>
              )}
              {!enhancementsLoading && !enhancementsError && enhancements !== null && enhancements.length === 0 && (
                <p style={{ margin: 0, color: "var(--color-text-muted)" }}>No significant changes detected.</p>
              )}
              {!enhancementsLoading && !enhancementsError && enhancements !== null && enhancements.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {enhancements.map((item, i) => (
                    <div key={i} style={{ border: "1px solid var(--color-card-border)", borderRadius: 8, padding: 16 }}>
                      <p className="card-title" style={{ fontSize: "var(--font-size-md)", marginBottom: 12 }}>{item.category}</p>
                      <div className="field-grid">
                        <div>
                          <p className="field-label">TW</p>
                          <div className="field-value">{item.tw_excerpt}</div>
                        </div>
                        <div>
                          <p className="field-label">LLM Generated</p>
                          <div className="field-value">{item.llm_excerpt}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
        */}

        {error && <p className="error-banner">{error}</p>}

        <div className="footer-actions">
          <button type="button" className="btn-primary" onClick={handleSaveAndNext} disabled={savingEdit}>
            {recordExists ? "Next" : "Save Problem Statement"}
          </button>
        </div>
      </div>

      {savingEdit && <GeneratingDialog heading="Saving Problem Statement" message="Persisting your edit — this only takes a moment." />}
      </>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card">
        <div style={{ maxWidth: 280 }}>
          <p className="field-label">Event Type</p>
          {recordExists ? (
            <div className="field-value">{eventType}</div>
          ) : (
            <select
              className="field-value"
              value={eventType}
              onChange={(e) => setEventType(e.target.value as EventType)}
            >
              {EVENT_TYPE_OPTIONS["problem-statement"].map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {sections.map(([section, sectionFields]) => (
        <div className="card" key={section}>
          <div className="card-header">
            <p className="card-title">{section}</p>
            <button
              type="button"
              className="collapse-chevron"
              onClick={() => toggleSection(section)}
              style={{ background: "none", border: "none", cursor: "pointer" }}
              aria-label={`Toggle ${section}`}
            >
              <img
                src={chevronEntry}
                alt=""
                width={20}
                height={20}
                style={{ transform: collapsed[section] ? "rotate(90deg)" : "rotate(-90deg)" }}
              />
            </button>
          </div>
          <p style={{ margin: "-8px 0 8px", fontSize: "var(--font-size-xs)", fontStyle: "italic", color: "var(--color-text-muted)" }}>
            (Pulled from TrackWise)
          </p>
          {!collapsed[section] && (
            <div className="field-grid" style={{ flexWrap: "wrap" }}>
              {sectionFields.map((field) => (
                <div key={field.key} style={{ minWidth: 240 }}>
                  <p className="field-label">
                    {field.label}
                    {field.required && " *"}
                  </p>
                  {recordExists ? (
                    <div className="field-value">{values[field.key] || "—"}</div>
                  ) : field.kind === "textarea" ? (
                    <textarea
                      className="field-value"
                      required={field.required}
                      value={values[field.key] ?? ""}
                      onChange={(e) => handleFieldChange(field.key, e.target.value)}
                    />
                  ) : (
                    <input
                      className="field-value"
                      type={nativeInputType(field.kind, values[field.key] ?? "")}
                      required={field.required}
                      value={values[field.key] ?? ""}
                      onChange={(e) => handleFieldChange(field.key, e.target.value)}
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {error && <p className="error-banner">{error}</p>}

      <div className="footer-actions">
        <button type="button" className="btn-primary" onClick={handleGenerate} disabled={submitting}>
          {submitting ? "Refining..." : "Refine Problem Statement"}
        </button>
      </div>
    </div>
  );
}
