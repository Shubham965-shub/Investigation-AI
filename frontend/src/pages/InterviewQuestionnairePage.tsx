import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { generateQuestionnaire, getProblemStatementRecord, getQuestionnaireRecord, updateQuestionnaireItems } from "../api/dashboard";
import { ApiError } from "../api/client";
import type { EventType, TrackwiseFields } from "../constants/trackwiseFields";
import { DbErrorModal } from "../components/DbErrorModal";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { AddItemDialog } from "../components/AddItemDialog";

interface ChecklistItem {
  description: string;
  checked: boolean;
  // Client-side only — distinguishes AI-generated suggestions (whether just
  // generated or loaded from a previously-persisted record) from items the
  // user typed in via "Add Your Own Question" in this session. Drives the
  // "can't deselect more than half the generated suggestions" cap below.
  isUserAdded: boolean;
}
import checkIcon from "../assets/icons/interview-checkbox.svg";
import addPlusIcon from "../assets/icons/interview-add-plus.svg";
import "./RecordModulePage.css";

export function InterviewQuestionnairePage() {
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();

  const [recordLoading, setRecordLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [problemStatement, setProblemStatement] = useState<string | null>(null);
  const [eventType, setEventType] = useState<EventType | undefined>(undefined);
  const [trackwiseFields, setTrackwiseFields] = useState<TrackwiseFields | undefined>(undefined);
  const [items, setItems] = useState<ChecklistItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [limitMessage, setLimitMessage] = useState<string | null>(null);

  // Everything comes from the DB — no localStorage. Interview Questionnaire
  // depends on the Problem Statement record existing (fetched here directly
  // rather than assumed from a prior page visit), plus its own record for
  // event_type/trackwise_fields/already-generated questions. A 404 on either
  // is a valid "not generated/no record yet" state; any other failure blocks
  // the page via DbErrorModal.
  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    setRecordLoading(true);
    setDbError(null);
    (async () => {
      try {
        const [psRecord, qRecord] = await Promise.all([
          getProblemStatementRecord(recordId),
          getQuestionnaireRecord(recordId),
        ]);
        if (cancelled) return;
        setProblemStatement(psRecord?.problem_statement ?? null);
        if (qRecord) {
          setEventType(qRecord.event_type);
          setTrackwiseFields(qRecord.trackwise_fields);
          if (qRecord.questions) {
            setItems(qRecord.questions.map((q) => ({ description: q.description, checked: q.is_checked ?? true, isUserAdded: false })));
          }
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

  useEffect(() => {
    if (!recordId || recordLoading || dbError || items !== null || !problemStatement || !eventType || !trackwiseFields) return;
    setLoading(true);
    setError(null);
    generateQuestionnaire(recordId, { event_type: eventType, trackwise_fields: trackwiseFields })
      .then((response) => {
        // Session-only display — the backend persists this (best-effort) as
        // part of the generate call.
        setItems(response.questions.map((q) => ({ description: q.description, checked: true, isUserAdded: false })));
      })
      .catch((err) => {
        setError(err instanceof ApiError ? String(err.detail) : "Failed to generate questionnaire");
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordId, recordLoading, dbError, problemStatement, eventType, trackwiseFields]);

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

  if (!problemStatement) {
    return (
      <div className="empty-state">
        <p>Complete the Problem Statement step first — Interview Questionnaire needs it to generate questions.</p>
        <button type="button" className="btn-primary" onClick={() => navigate(`/records/${recordId}/problem-statement`)}>
          Go to Problem Statement
        </button>
      </div>
    );
  }

  // Persisted best-effort on every toggle/add — a failed PUT is logged but
  // never blocks the UI; the change stays reflected locally either way.
  function persistItems(list: ChecklistItem[]) {
    if (!recordId) return;
    updateQuestionnaireItems(
      recordId,
      list.map((i) => ({ description: i.description, is_new: false, is_checked: i.checked }))
    ).catch((err) => {
      console.error("Failed to persist questionnaire items", err);
    });
  }

  // Deselection cap: the user can't uncheck more than half of the AI-
  // generated suggestions (isUserAdded: false) — user-added questions are
  // exempt in both directions, and re-checking a generated item is always
  // allowed since it only lowers the deselected count.
  function toggleItem(index: number) {
    if (!items) return;
    const item = items[index];
    if (!item.isUserAdded && item.checked) {
      const generatedCount = items.filter((i) => !i.isUserAdded).length;
      const maxDeselectable = Math.floor(generatedCount / 2);
      const deselectedCount = items.filter((i) => !i.isUserAdded && !i.checked).length;
      if (deselectedCount + 1 > maxDeselectable) {
        setLimitMessage(`You can't deselect more than half of the generated questions (max ${maxDeselectable}).`);
        return;
      }
    }
    setLimitMessage(null);
    const newItems = items.map((it, i) => (i === index ? { ...it, checked: !it.checked } : it));
    setItems(newItems);
    persistItems(newItems);
  }

  function addItem(name: string) {
    setShowAddDialog(false);
    const newItems = [...(items ?? []), { description: name, checked: true, isUserAdded: true }];
    setItems(newItems);
    persistItems(newItems);
  }

  function handleAgreeAndCopy() {
    setShowConfirm(false);
    setSaved(true);
    setTimeout(() => {
      setSaved(false);
      navigate(`/records/${recordId}/rci-plan`);
    }, 1500);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, position: "relative" }}>
      <div className="card">
        <p className="card-title">Problem Statement</p>
        <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12 }}>
          <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-md)", lineHeight: 1.9 }}>{problemStatement}</p>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="card-header">
          <p className="card-title">Recommended Interview Questionnaire</p>
        </div>

        <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-md)" }}>Note: You may uncheck if any question is not required in this investigation.</p>

        {loading && <p style={{ color: "var(--color-text-muted)" }}>Generating interview questions…</p>}
        {error && <p className="error-banner">{error}</p>}
        {limitMessage && <p className="error-banner">{limitMessage}</p>}

        {items && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {items.map((item, index) => (
              <div className="checklist-row" key={index} style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
                <div style={{ display: "flex", gap: 12, alignItems: "flex-start", width: "100%" }}>
                  <button
                    type="button"
                    className={`checklist-checkbox ${item.checked ? "" : "unchecked"}`}
                    onClick={() => toggleItem(index)}
                    aria-label={item.checked ? "Uncheck" : "Check"}
                  >
                    {item.checked && <img src={checkIcon} alt="" width={12} height={12} />}
                  </button>
                  <span className="checklist-text">{item.description}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="footer-actions split">
        <button type="button" className="btn-secondary" onClick={() => setShowAddDialog(true)}>
          <img src={addPlusIcon} alt="" width={16} height={16} />
          Add Your Own Question
        </button>
        <button type="button" className="btn-primary" onClick={() => setShowConfirm(true)}>
          {saved ? "Saved" : "Agree & Copy"}
        </button>
      </div>

      {showAddDialog && (
        <AddItemDialog
          title="Add Question"
          label="Question"
          placeholder="Enter Question"
          confirmLabel="Add Question"
          onCancel={() => setShowAddDialog(false)}
          onConfirm={addItem}
        />
      )}

      {showConfirm && (
        <ConfirmDialog
          title="Accept Interview Questionnaire?"
          message="Are you sure you want to accept the Interview Questionnaire and lock it for this investigation?"
          onCancel={() => setShowConfirm(false)}
          onConfirm={handleAgreeAndCopy}
        />
      )}
    </div>
  );
}
