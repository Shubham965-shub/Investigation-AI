import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getTaskCritique,
  uploadTaskCritiqueReport,
  uploadTaskCritiqueSourceDocument,
  type TaskCritiqueSection,
} from "../api/dashboard";
import { ApiError } from "../api/client";
import { DbErrorModal } from "../components/DbErrorModal";
import { FileDropzone } from "../components/FileDropzone";
import exportIcon from "../assets/icons/rci-export-icon.svg";
import "./RecordModulePage.css";

const STATUS_LABEL: Record<TaskCritiqueSection["status"], string> = {
  pending: "Pending",
  in_progress: "In Progress",
  complete: "Complete",
};

export function TaskCritiquePage() {
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [sections, setSections] = useState<TaskCritiqueSection[] | null>(null);
  const [hasSourceDocument, setHasSourceDocument] = useState(false);
  const [sourceDocError, setSourceDocError] = useState<string | null>(null);
  const [sourceDocUploading, setSourceDocUploading] = useState(false);
  const [busyTaskIndex, setBusyTaskIndex] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<Record<number, string>>({});

  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    setLoading(true);
    setDbError(null);
    (async () => {
      try {
        const data = await getTaskCritique(recordId);
        if (cancelled) return;
        setSections(data?.sections ?? null);
        setHasSourceDocument(data?.has_source_document ?? false);
      } catch (err) {
        if (!cancelled) setDbError(err instanceof ApiError ? String(err.detail) : "Could not reach the database.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [recordId, retryKey]);

  if (!recordId) return null;

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

  async function handleSourceDocumentUpload(file: File) {
    setSourceDocUploading(true);
    setSourceDocError(null);
    try {
      const data = await uploadTaskCritiqueSourceDocument(recordId!, file);
      setSections(data.sections);
      setHasSourceDocument(data.has_source_document);
    } catch (err) {
      setSourceDocError(err instanceof ApiError ? String(err.detail) : "Failed to read this document");
    } finally {
      setSourceDocUploading(false);
    }
  }

  if (!hasSourceDocument) {
    return (
      <div className="card" style={{ gap: 12 }}>
        <p className="card-title">Upload RCI Plan Report</p>
        <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
          No RCI Plan document has been exported for this investigation yet. Upload the RCI Plan report to extract its tasks for
          critique, or go generate/export one from RCI Plan Creation first.
        </p>
        <FileDropzone disabled={sourceDocUploading} onFileSelected={handleSourceDocumentUpload} />
        {sourceDocError && <p className="error-banner">{sourceDocError}</p>}
        <div className="footer-actions">
          <button type="button" className="btn-outline" onClick={() => navigate(`/records/${recordId}/rci-plan`)}>
            Go to RCI Plan Creation
          </button>
        </div>
      </div>
    );
  }

  async function handleUpload(taskIndex: number, file: File) {
    setBusyTaskIndex(taskIndex);
    setUploadError((prev) => ({ ...prev, [taskIndex]: "" }));
    try {
      const updated = await uploadTaskCritiqueReport(recordId!, taskIndex, file);
      if (updated.locked) {
        // Final upload (gospel or 3rd attempt) — scored, nothing left to
        // review, so stay on the main list page instead of jumping to the
        // detail page.
        setSections((prev) => (prev ? prev.map((s) => (s.task_index === taskIndex ? updated : s)) : prev));
        setBusyTaskIndex(null);
      } else {
        navigate(`/records/${recordId}/task-critique/${taskIndex}`);
      }
    } catch (err) {
      setUploadError((prev) => ({
        ...prev,
        [taskIndex]: err instanceof ApiError ? String(err.detail) : "Failed to upload report",
      }));
      setBusyTaskIndex(null);
    }
  }

  if (!sections || sections.length === 0) {
    return (
      <div className="empty-state">
        <p>No tasks could be found in this investigation's RCI Plan document.</p>
      </div>
    );
  }

  const allComplete = sections.every((s) => s.status === "complete");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card-header">
        <p className="card-title">Task Critique History</p>
        <button
          type="button"
          className="btn-primary"
          style={{ display: "flex", alignItems: "center", gap: 10, opacity: allComplete ? 1 : 0.4, cursor: allComplete ? "pointer" : "default" }}
          disabled={!allComplete}
          onClick={() => navigate(`/records/${recordId}/rc-capa-critique`)}
        >
          <img src={exportIcon} alt="" width={16} height={16} />
          Agree and Push to RC & CAPA Critique
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {sections.map((section, index) => {
          const busy = busyTaskIndex === section.task_index;
          const hasScore = section.status === "complete" && section.latest_report?.task_score != null;
          return (
            <div key={section.task_index} className="card" style={{ padding: 0, gap: 0, overflow: "hidden" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 20, padding: "12px 16px" }}>
                <div
                  style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8, cursor: "pointer" }}
                  onClick={() => navigate(`/records/${recordId}/task-critique/${section.task_index}`)}
                >
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: "var(--font-size-base)" }}>
                      {index + 1}. {section.title}
                    </span>
                    <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                      ({section.task_count} {section.task_count === 1 ? "task" : "tasks"})
                    </span>
                  </div>
                  {section.correlation && (
                    <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-faint)" }}>{section.correlation}</p>
                  )}
                  <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                    <span className={`status-pill ${section.status}`}>{STATUS_LABEL[section.status]}</span>
                    <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", display: "flex", alignItems: "center", gap: 6, boxSizing: "border-box" }}>
                      <span style={{ fontSize: "var(--font-size-md)", color: "var(--color-text-faint)" }}>{section.assignee || "Unassigned"}</span>
                    </div>
                    <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", boxSizing: "border-box" }}>
                      <span style={{ fontSize: "var(--font-size-md)", color: "var(--color-text-faint)" }}>TCD: {section.due_date || "—"}</span>
                    </div>
                  </div>
                </div>

                <div style={{ flexShrink: 0, minWidth: 180 }} onClick={(e) => e.stopPropagation()}>
                  {section.can_upload && (
                    <FileDropzone compact disabled={busy} label="Upload Report" onFileSelected={(file) => handleUpload(section.task_index, file)} />
                  )}
                  {hasScore && (
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 8,
                        padding: "16px 24px",
                        borderRadius: 6,
                        background: "var(--color-success-bg)",
                        border: "1px solid var(--color-success-text)",
                      }}
                    >
                      <div
                        style={{
                          width: 36,
                          height: 36,
                          borderRadius: "50%",
                          border: "1.5px solid var(--color-success-text)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          flexShrink: 0,
                        }}
                      >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--color-success-text)" }}>
                          <path d="M8 21h8M12 17v4M7 4h10v4a5 5 0 0 1-10 0V4Z" strokeLinecap="round" strokeLinejoin="round" />
                          <path d="M7 5H4a1 1 0 0 0-1 1v1a4 4 0 0 0 4 4M17 5h3a1 1 0 0 1 1 1v1a4 4 0 0 1-4 4" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </div>
                      <div style={{ textAlign: "center" }}>
                        <p style={{ margin: 0, fontSize: "var(--font-size-xs)", fontWeight: 700, letterSpacing: "0.08em", color: "var(--color-text-muted)", textTransform: "uppercase" }}>
                          Task Score
                        </p>
                        <p style={{ margin: 0, fontSize: "1.5rem", fontWeight: 700 }}>{section.latest_report!.task_score}%</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {section.can_upload && (section.next_upload_is_final || uploadError[section.task_index]) && (
                <div style={{ padding: "0 16px 12px" }}>
                  {section.next_upload_is_final && (
                    <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-warning-text)" }}>
                      All recommendations were rejected — the next report you upload will be accepted as final, with no further review.
                    </p>
                  )}
                  {uploadError[section.task_index] && <p className="error-banner" style={{ margin: "8px 0 0" }}>{uploadError[section.task_index]}</p>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}