import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  EVENT_TYPE_OPTIONS,
  getFieldSet,
  nativeInputType,
  type EventType,
  type TrackwiseFields,
} from "../constants/trackwiseFields";
import { generateProblemStatement, getProblemStatementRecord } from "../api/dashboard";
import { ApiError } from "../api/client";
import { RecordDetailsModal } from "../components/RecordDetailsModal";
import { DbErrorModal } from "../components/DbErrorModal";
import { ProblemStatementGuidelines } from "../components/ProblemStatementGuidelines";
import copyIcon from "../assets/icons/copy-icon.svg";
import chevronEntry from "../assets/icons/chevron-entry.svg";
import chevronA from "../assets/icons/chevron-a.svg";
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
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [eventType, setEventType] = useState<EventType>(EVENT_TYPE_OPTIONS["problem-statement"][0]);
  // True once a real DB record was found for this id — even if its
  // problem_statement itself hasn't been generated yet, trackwise_fields
  // already reflects real (Trackwise-sourced) data at that point, so the
  // entry form below switches those fields to read-only instead of letting
  // the user edit already-committed DB data through this form.
  const [recordExists, setRecordExists] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [problemStatement, setProblemStatement] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  // Shown automatically any time the generated view appears — whether from
  // a fresh generation this session or landing on an already-generated
  // record (matches Figma's "Home<Problem_Statement_Generated" modal).
  const [showSummaryModal, setShowSummaryModal] = useState(false);

  // Real event_type/trackwise_fields/problem_statement come from the DB only
  // — no localStorage fallback. A 404 (no record yet) is a valid, non-error
  // state and falls through to the blank entry-form defaults already in
  // state. Any other failure blocks the page entirely via DbErrorModal.
  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    setLoading(true);
    setDbError(null);
    (async () => {
      try {
        const record = await getProblemStatementRecord(recordId);
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
  }, [recordId, retryKey]);

  useEffect(() => {
    if (problemStatement) setShowSummaryModal(true);
  }, [problemStatement]);

  const fields = useMemo(() => getFieldSet("problem-statement", eventType), [eventType]);
  const sections = useMemo(() => groupBySection(fields), [fields]);

  if (!recordId) return null;
  const rid: string = recordId;

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
      const response = await generateProblemStatement(rid, { event_type: eventType, trackwise_fields: trackwiseFields });
      // Session-only display — the backend already persists this (best-effort)
      // as part of the generate call; no client-side cache to update here.
      setProblemStatement(response.problem_statement);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Failed to generate problem statement");
    } finally {
      setSubmitting(false);
    }
  }

  function handleCopy() {
    if (!problemStatement) return;
    navigator.clipboard.writeText(problemStatement).then(() => {
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
        navigate(`/records/${rid}/evidence-collection`);
      }, 1500);
    });
  }

  function handleCloseAndNext() {
    navigate(`/records/${rid}/evidence-collection`);
  }

  if (problemStatement) {
    return (
      <>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="card">
          <div className="card-header">
            <p className="card-title">Problem Statement <ProblemStatementGuidelines /></p>
            <button type="button" className="btn-outline" onClick={handleCopy}>
              <img src={copyIcon} alt="" width={18} height={18} />
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p style={{ margin: "-8px 0 8px", fontSize: "var(--font-size-xs)", fontStyle: "italic", color: "var(--color-text-muted)" }}>
            (Generated by LLM)
          </p>
          <div style={{ background: "var(--color-bg)", borderRadius: 4, padding: 12 }}>
            <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-lg)", lineHeight: 1.8 }}>{problemStatement}</p>
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
                  src={chevronA}
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
                    <div className="field-value">{values[field.key] || "—"}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        <div className="footer-actions">
          <button type="button" className="btn-primary" onClick={handleCloseAndNext}>
            Close &amp; Next
          </button>
        </div>
      </div>

      {showSummaryModal && (
        <RecordDetailsModal
          recordId={rid}
          problemStatement={problemStatement}
          onClose={() => setShowSummaryModal(false)}
          onSaveEdit={(newText) => {
            // Session-only — no backend endpoint yet to persist an edit to an
            // already-generated problem statement.
            setProblemStatement(newText);
          }}
          onSaveAndNext={handleCloseAndNext}
          onViewRecordDetails={() => setShowSummaryModal(false)}
        />
      )}
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
          {submitting ? "Generating…" : "Save & Generate Problem Statement"}
        </button>
      </div>
    </div>
  );
}
