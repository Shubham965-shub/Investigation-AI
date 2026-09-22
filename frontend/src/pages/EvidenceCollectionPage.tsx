import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { collectEvidence, getEvidenceRecord, getProblemStatementRecord, updateEvidenceItems } from "../api/dashboard";
import { ApiError } from "../api/client";
import type { EventType, TrackwiseFields } from "../constants/trackwiseFields";
import { DbErrorModal } from "../components/DbErrorModal";
import { GeneratingDialog } from "../components/GeneratingDialog";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { AddItemDialog } from "../components/AddItemDialog";

interface ChecklistItem {
  description: string;
  checked: boolean;
  // Distinguishes AI-generated suggestions from user-added items — drives the "can't deselect more than half" cap below.
  isUserAdded: boolean;
}
import checkIcon from "../assets/icons/evidence-checkbox.svg";
import viewListIcon from "../assets/icons/evidence-view-list.svg";
import viewGridIcon from "../assets/icons/evidence-view-grid.svg";
import addPlusIcon from "../assets/icons/evidence-add-plus.svg";
import copyIcon from "../assets/icons/copy-icon.svg";
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
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [limitMessage, setLimitMessage] = useState<string | null>(null);

  // Depends on the Problem Statement record existing — a 404 on either fetch is a valid "not generated yet" state; any other failure blocks the page via DbErrorModal.
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
            setItems(evRecord.evidence.map((e) => ({ description: e.description, checked: e.is_checked ?? true, isUserAdded: e.is_new ?? false })));
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
        // Session-only display — the backend persists this (best-effort) as part of the collect call.
        setItems(response.evidence.map((e) => ({ description: e.description, checked: true, isUserAdded: false })));
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

  // Best-effort persist — a failed PUT is logged but never blocks the UI.
  function persistItems(list: ChecklistItem[]) {
    if (!recordId) return;
    updateEvidenceItems(
      recordId,
      list.map((i) => ({ description: i.description, is_new: i.isUserAdded, is_checked: i.checked }))
    ).catch((err) => {
      console.error("Failed to persist evidence items", err);
    });
  }

  // Can't uncheck more than half of the AI-generated suggestions; user-added evidence is exempt.
  function toggleItem(index: number) {
    if (!items) return;
    const item = items[index];
    if (!item.isUserAdded && item.checked) {
      const generatedCount = items.filter((i) => !i.isUserAdded).length;
      const maxDeselectable = Math.floor(generatedCount / 2);
      const deselectedCount = items.filter((i) => !i.isUserAdded && !i.checked).length;
      if (deselectedCount + 1 > maxDeselectable) {
        setLimitMessage(`You can't deselect more than half of the generated evidence (max ${maxDeselectable}).`);
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

  function handleAgreeAndNext() {
    setShowConfirm(false);
    setSaved(true);
    setTimeout(() => {
      setSaved(false);
      navigate(`/records/${recordId}/interview-questionnaire`);
    }, 1500);
  }

  function showCopied(index: number) {
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex((prev) => (prev === index ? null : prev)), 1200);
  }

  function handleCopyItem(index: number, description: string) {
    navigator.clipboard.writeText(description).then(() => {
      if (copiedIndex === index) {
        // Flash back to "Copy" briefly first, so re-clicking while already copied is visibly acknowledged.
        setCopiedIndex(null);
        setTimeout(() => showCopied(index), 150);
      } else {
        showCopied(index);
      }
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card">
        <p className="card-title">Problem Statement</p>
        <div style={{ background: "var(--color-bg)", borderRadius: 4, padding: 12 }}>
          <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-md)", lineHeight: 1.9 }}>{problemStatement}</p>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="card-header">
          <p className="card-title" style={{ fontWeight: 700 }}>Recommended Evidences To Be Collected</p>
          <div style={{ display: "flex", gap: 4, background: "var(--color-open-bg)", padding: 4, borderRadius: 10 }}>
            <button
              type="button"
              onClick={() => setView("list")}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 8, border: "none", background: view === "list" ? "var(--color-surface)" : "transparent", fontSize: "var(--font-size-sm)", fontWeight: 500, color: view === "list" ? "var(--color-primary)" : "var(--color-text-muted)" }}
            >
              <img src={viewListIcon} alt="" width={14} height={14} /> list
            </button>
            <button
              type="button"
              onClick={() => setView("grid")}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 8, border: "none", background: view === "grid" ? "var(--color-surface)" : "transparent", fontSize: "var(--font-size-sm)", fontWeight: 500, color: view === "grid" ? "var(--color-primary)" : "var(--color-text-muted)" }}
            >
              <img src={viewGridIcon} alt="" width={14} height={14} /> grid
            </button>
          </div>
        </div>
        <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-md)" }}>Note: You may uncheck if any of the evidence is not required in this investigation.</p>
        <p style={{ margin: 0, fontSize: "var(--font-size-sm)", fontStyle: "italic", color: "var(--color-text-muted)" }}>These recommendations are generated from a rule-based library.</p>

        {loading && (
          <GeneratingDialog
            heading="Generating evidence…"
            message="Recommended evidence items for this investigation are being generated — this can take a moment."
          />
        )}
        {error && <p className="error-banner">{error}</p>}
        {limitMessage && <p className="error-banner">{limitMessage}</p>}

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
                <button
                  type="button"
                  className="btn-outline"
                  style={{ flexShrink: 0, padding: "6px 10px", display: "flex", alignItems: "center", gap: 6 }}
                  onClick={() => handleCopyItem(index, item.description)}
                  aria-label={copiedIndex === index ? "Copied" : "Copy"}
                  title={copiedIndex === index ? "Copied" : "Copy"}
                >
                  <img src={copyIcon} alt="" width={14} height={14} />
                  {copiedIndex === index && "Copied"}
                </button>
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
          {saved ? "Saved" : "Agree and Next"}
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
          onCancel={() => setShowConfirm(false)}
          onConfirm={handleAgreeAndNext}
        />
      )}
    </div>
  );
}
