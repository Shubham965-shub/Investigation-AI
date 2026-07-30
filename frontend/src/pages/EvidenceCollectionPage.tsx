import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { collectEvidence, getEvidenceRecord, getProblemStatementRecord } from "../api/dashboard";
import { ApiError } from "../api/client";
import type { EventType, TrackwiseFields } from "../constants/trackwiseFields";
import { DbErrorModal } from "../components/DbErrorModal";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { AddItemDialog } from "../components/AddItemDialog";

interface ChecklistItem {
  description: string;
  checked: boolean;
}
import checkIcon from "../assets/icons/evidence-checkbox.svg";
import viewListIcon from "../assets/icons/evidence-view-list.svg";
import viewGridIcon from "../assets/icons/evidence-view-grid.svg";
import addPlusIcon from "../assets/icons/evidence-add-plus.svg";
import "./RecordModulePage.css";

export function EvidenceCollectionPage() {
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();

  const [recordLoading, setRecordLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [problemStatement, setProblemStatement] = useState<string | null>(null);
  const [eventType, setEventType] = useState<EventType | undefined>(undefined);
  const [trackwiseFields, setTrackwiseFields] = useState<TrackwiseFields | undefined>(undefined);
  const [items, setItems] = useState<ChecklistItem[] | null>(null);
  const [view, setView] = useState<"list" | "grid">("list");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [showAddDialog, setShowAddDialog] = useState(false);

  // Everything comes from the DB — no localStorage. Evidence Collection
  // depends on the Problem Statement record existing (fetched here directly
  // rather than assumed from a prior page visit), plus its own record for
  // event_type/trackwise_fields/already-generated evidence. A 404 on either
  // is a valid "not generated/no record yet" state; any other failure blocks
  // the page via DbErrorModal.
  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    setRecordLoading(true);
    setDbError(null);
    (async () => {
      try {
        const [psRecord, evRecord] = await Promise.all([
          getProblemStatementRecord(recordId),
          getEvidenceRecord(recordId),
        ]);
        if (cancelled) return;
        setProblemStatement(psRecord?.problem_statement ?? null);
        if (evRecord) {
          setEventType(evRecord.event_type);
          setTrackwiseFields(evRecord.trackwise_fields);
          if (evRecord.evidence) {
            setItems(evRecord.evidence.map((e) => ({ description: e.description, checked: e.is_checked ?? true })));
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
    collectEvidence(recordId, { event_type: eventType, trackwise_fields: trackwiseFields })
      .then((response) => {
        // Session-only display — the backend persists this (best-effort) as
        // part of the collect call.
        setItems(response.evidence.map((e) => ({ description: e.description, checked: true })));
      })
      .catch((err) => {
        setError(err instanceof ApiError ? String(err.detail) : "Failed to collect evidence");
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
        <p>Complete the Problem Statement step first — Evidence Collection needs it to generate recommendations.</p>
        <button type="button" className="btn-primary" onClick={() => navigate(`/records/${recordId}/problem-statement`)}>
          Go to Problem Statement
        </button>
      </div>
    );
  }

  // Session-only — no backend endpoint yet to persist individual
  // toggle/add-item edits; a refresh reverts to the last generated/DB state.
  function toggleItem(index: number) {
    setItems((prev) => {
      if (!prev) return prev;
      return prev.map((item, i) => (i === index ? { ...item, checked: !item.checked } : item));
    });
  }

  function addItem(name: string) {
    setShowAddDialog(false);
    setItems((prev) => [...(prev ?? []), { description: name, checked: true }]);
  }

  function handleAgreeAndCopy() {
    setShowConfirm(false);
    setSaved(true);
    setTimeout(() => {
      setSaved(false);
      navigate(`/records/${recordId}/interview-questionnaire`);
    }, 1500);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card">
        <p className="card-title">Problem Statement</p>
        <div style={{ background: "var(--color-bg)", borderRadius: 4, padding: 12 }}>
          <p style={{ margin: 0, fontWeight: 600, fontSize: 16, lineHeight: 1.9 }}>{problemStatement}</p>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="card-header">
          <p className="card-title" style={{ fontWeight: 700 }}>Recommended Evidence List</p>
          <div style={{ display: "flex", gap: 4, background: "var(--color-open-bg)", padding: 4, borderRadius: 10 }}>
            <button
              type="button"
              onClick={() => setView("list")}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 8, border: "none", background: view === "list" ? "#fff" : "transparent", fontSize: 12, fontWeight: 500, color: view === "list" ? "var(--color-primary)" : "var(--color-text-muted)" }}
            >
              <img src={viewListIcon} alt="" width={14} height={14} /> list
            </button>
            <button
              type="button"
              onClick={() => setView("grid")}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 8, border: "none", background: view === "grid" ? "#fff" : "transparent", fontSize: 12, fontWeight: 500, color: view === "grid" ? "var(--color-primary)" : "var(--color-text-muted)" }}
            >
              <img src={viewGridIcon} alt="" width={14} height={14} /> grid
            </button>
          </div>
        </div>
        <p style={{ margin: 0, fontWeight: 600, fontSize: 16 }}>Note: You may uncheck if any of the evidence is not required in this investigation.</p>

        {loading && <p style={{ color: "var(--color-text-muted)" }}>Generating recommended evidence…</p>}
        {error && <p className="error-banner">{error}</p>}

        {items && (
          <div style={view === "grid" ? { display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 } : { display: "flex", flexDirection: "column", gap: 8 }}>
            {items.map((item, index) => (
              <div className="checklist-row" key={index}>
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
            ))}
          </div>
        )}
      </div>

      <div className="footer-actions split">
        <button type="button" className="btn-secondary" onClick={() => setShowAddDialog(true)}>
          <img src={addPlusIcon} alt="" width={16} height={16} />
          Add Evidence
        </button>
        <button type="button" className="btn-primary" onClick={() => setShowConfirm(true)}>
          {saved ? "Saved" : "Agree & Copy"}
        </button>
      </div>

      {showAddDialog && (
        <AddItemDialog
          title="Add Evidence"
          label="Evidence Name"
          placeholder="Enter Evidence Name"
          confirmLabel="Add Evidence"
          onCancel={() => setShowAddDialog(false)}
          onConfirm={addItem}
        />
      )}

      {showConfirm && (
        <ConfirmDialog
          title="Accept Evidence Collection?"
          message="Are you sure you want to accept the Evidence Collection and lock it for this investigation?"
          onCancel={() => setShowConfirm(false)}
          onConfirm={handleAgreeAndCopy}
        />
      )}
    </div>
  );
}
