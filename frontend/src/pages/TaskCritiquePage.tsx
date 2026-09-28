import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getProblemStatementRecord,
  getTaskCritique,
  uploadTaskCritiqueReport,
  uploadTaskCritiqueSourceDocument,
  type TaskCritiqueSection,
} from "../api/dashboard";
import { ApiError } from "../api/client";
import { DbErrorModal } from "../components/DbErrorModal";
import { FileDropzone } from "../components/FileDropzone";
import { TaskCritiqueGuidelines } from "../components/TaskCritiqueGuidelines";
import { ScoreBreakdownTooltip } from "../components/ScoreBreakdownTooltip";
import { ScoringDialog, type ScoringReason } from "../components/ScoringDialog";
import { scoreGrade } from "../utils/scoreGrade";
import { recordPath, fromRciSegment } from "../lib/rci";
import { track, EVENTS } from "../telemetry/events";
import exportIcon from "../assets/icons/rci-export-icon.svg";
import "./RecordModulePage.css";

const STATUS_LABEL: Record<TaskCritiqueSection["status"], string> = {
  pending: "Pending",
  processing: "Processing",
  in_progress: "In Progress",
  complete: "Complete",
};

export function TaskCritiquePage() {
  const { recordId, rciId } = useParams<{ recordId: string; rciId: string }>();
  const normalizedRciId = fromRciSegment(rciId) || null;
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [sections, setSections] = useState<TaskCritiqueSection[] | null>(null);
  const [problemStatement, setProblemStatement] = useState<string | null>(null);
  const [hasSourceDocument, setHasSourceDocument] = useState(false);
  const [sourceDocError, setSourceDocError] = useState<string | null>(null);
  const [sourceDocUploading, setSourceDocUploading] = useState(false);
  const [busyTaskIndex, setBusyTaskIndex] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<Record<number, string>>({});
  const [scoring, setScoring] = useState<ScoringReason | null>(null);

  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    setLoading(true);
    setDbError(null);
    (async () => {
      try {
        const [data, psRecord] = await Promise.all([
          getTaskCritique(recordId, normalizedRciId),
          getProblemStatementRecord(recordId, normalizedRciId),
        ]);
        if (cancelled) return;
        setSections(data?.sections ?? null);
        setHasSourceDocument(data?.has_source_document ?? false);
        setProblemStatement(psRecord?.problem_statement ?? null);
      } catch (err) {
        if (!cancelled) setDbError(err instanceof ApiError ? String(err.detail) : "Could not reach the database.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [recordId, rciId, retryKey]);

  // Single shared poll loop covering every section, not one interval per task — the upload endpoint
  // now returns almost immediately with status "processing" while DS critique/scoring runs in the
  // background (Azure was killing the connection on the old synchronous call before DS could finish).
  // Keeps polling as long as ANY section is still processing, so uploading to a second task while the
  // first is still processing doesn't spawn a second overlapping interval. Stops itself (via the
  // dependency on `sections`) the moment a poll comes back with nothing left in "processing".
  useEffect(() => {
    if (!recordId) return;
    const hasProcessing = (sections ?? []).some(
      (s) => s.status === "processing" || s.latest_report?.critique_pending
    );
    if (!hasProcessing) return;
    const intervalId = setInterval(() => {
      getTaskCritique(recordId, normalizedRciId)
        .then((data) => {
          if (data) {
            // Fire taskCritiqueUploadResolved exactly once per task_index, the moment it transitions
            // OUT of "processing" — comparing this closure's `sections` (the previous poll tick's
            // state) against the freshly fetched data naturally prevents re-firing on later ticks,
            // since the next effect instance's closure will already reflect the resolved state.
            const prevProcessing = new Set(
              (sections ?? [])
                .filter((s) => s.status === "processing" || s.latest_report?.critique_pending)
                .map((s) => s.task_index)
            );
            for (const s of data.sections) {
              const stillProcessing = s.status === "processing" || s.latest_report?.critique_pending;
              if (prevProcessing.has(s.task_index) && !stillProcessing) {
                track(EVENTS.taskCritiqueUploadResolved, {
                  recordId,
                  rciId: normalizedRciId,
                  taskIndex: s.task_index,
                  status: s.latest_report?.critique_failed ? "critique_failed" : "complete",
                });
              }
            }
            setSections(data.sections);
          }
        })
        .catch(() => {
          // Transient poll failure — the interval keeps running and retries on the next tick.
        });
    }, 3500);
    return () => clearInterval(intervalId);
  }, [recordId, normalizedRciId, sections]);

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
      const data = await uploadTaskCritiqueSourceDocument(recordId!, normalizedRciId, file);
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
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {problemStatement && (
          <div className="card">
            <p className="card-title">Problem Statement</p>
            <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12 }}>
              <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-md)", lineHeight: 1.9 }}>{problemStatement}</p>
            </div>
          </div>
        )}
        <div className="card" style={{ gap: 12 }}>
          <p className="card-title">Upload RCI Plan Report</p>
          <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
            No RCI Plan document has been exported for this investigation yet. Upload the RCI Plan report to extract its tasks for
            critique, or go generate/export one from RCI Plan Creation first.
          </p>
          <FileDropzone disabled={sourceDocUploading} loading={sourceDocUploading} onFileSelected={handleSourceDocumentUpload} />
          {sourceDocError && <p className="error-banner">{sourceDocError}</p>}
          <div className="footer-actions">
            <button type="button" className="btn-outline" onClick={() => navigate(recordPath(recordId, normalizedRciId, "rci-plan"))}>
              Go to RCI Plan Creation
            </button>
          </div>
        </div>
      </div>
    );
  }

  async function handleUpload(taskIndex: number, file: File) {
    setBusyTaskIndex(taskIndex);
    setUploadError((prev) => ({ ...prev, [taskIndex]: "" }));
    // Predicted client-side — a gospel upload or the final attempt both lock and score synchronously in this same request.
    const section = sections?.find((s) => s.task_index === taskIndex);
    if (section?.next_upload_is_final) {
      setScoring("gospel");
    } else if (section && section.upload_count + 1 >= section.max_uploads) {
      setScoring("final_attempt");
    }
    track(EVENTS.taskCritiqueUploaded, { recordId, rciId: normalizedRciId, taskIndex });
    try {
      const updated = await uploadTaskCritiqueReport(recordId!, normalizedRciId, taskIndex, file);
      if (updated.locked) {
        // Final upload — nothing left to review, so stay on the list page instead of navigating to the detail page.
        setSections((prev) => (prev ? prev.map((s) => (s.task_index === taskIndex ? updated : s)) : prev));
        setBusyTaskIndex(null);
        setScoring(null);
      } else {
        navigate(recordPath(recordId!, normalizedRciId, `task-critique/${taskIndex}`));
      }
    } catch (err) {
      setUploadError((prev) => ({
        ...prev,
        [taskIndex]: err instanceof ApiError ? String(err.detail) : "Failed to upload report",
      }));
      setBusyTaskIndex(null);
      setScoring(null);
    }
  }

  if (!sections || sections.length === 0) {
    return (
      <div className="empty-state">
        <p>No tasks could be found in this investigation's RCI Plan document.</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {problemStatement && (
        <div className="card">
          <p className="card-title">Problem Statement</p>
          <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12 }}>
            <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-md)", lineHeight: 1.9 }}>{problemStatement}</p>
          </div>
        </div>
      )}
      <div className="card-header">
        <p className="card-title">Task Critique <TaskCritiqueGuidelines /></p>
        <button
          type="button"
          className="btn-primary"
          style={{ display: "flex", alignItems: "center", gap: 10 }}
          onClick={() => navigate(recordPath(recordId, normalizedRciId, "rc-capa-critique"))}
        >
          <img src={exportIcon} alt="" width={16} height={16} />
          Agree and Push to RC, Impact & CAPA Critique
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
                  onClick={() => navigate(recordPath(recordId, normalizedRciId, `task-critique/${section.task_index}`))}
                >
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: "var(--font-size-base)" }}>
                      {index + 1}. {section.title}
                    </span>
                  </div>
                  {section.correlation && (
                    <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-faint)" }}>{section.correlation}</p>
                  )}
                  <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                    <span className={`status-pill ${section.status}`}>{STATUS_LABEL[section.status]}</span>
                    {section.upload_count > 0 && (
                      <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                        Attempt {section.upload_count} of {section.max_uploads}
                      </span>
                    )}
                    {section.latest_report && (
                      <>
                        <div style={{ background: "var(--color-open-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", display: "flex", alignItems: "center", gap: 6, boxSizing: "border-box" }}>
                          <span style={{ fontSize: "var(--font-size-md)", color: "var(--color-text-faint)" }}>{section.assignee || "Unassigned"}</span>
                        </div>
                        <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", boxSizing: "border-box" }}>
                          <span style={{ fontSize: "var(--font-size-md)", color: "var(--color-text-faint)" }}>TCD: {section.due_date || "—"}</span>
                        </div>
                      </>
                    )}
                    {uploadError[section.task_index] && (
                      <span
                        className="error-badge"
                        title={uploadError[section.task_index]}
                        style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                      >
                        ⚠ {uploadError[section.task_index]}
                      </span>
                    )}
                    {!uploadError[section.task_index] && section.latest_report?.critique_failed && (
                      <span
                        className="error-badge"
                        title="This report couldn't be reviewed — it doesn't match the required task report format. Please re-upload the correct report."
                      >
                        ⚠ Critique failed — wrong format
                      </span>
                    )}
                  </div>
                </div>

                <div style={{ flexShrink: 0, minWidth: 180 }} onClick={(e) => e.stopPropagation()}>
                  {section.can_upload && (
                    <FileDropzone compact disabled={busy} loading={busy} label="Upload Task Report" onFileSelected={(file) => handleUpload(section.task_index, file)} />
                  )}
                  {(section.status === "processing" || section.latest_report?.critique_pending) && (
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: "16px 8px" }}>
                      <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2, color: "var(--color-primary)" }} />
                      <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>Analyzing report…</span>
                    </div>
                  )}
                  {hasScore && (() => {
                    const grade = scoreGrade(section.latest_report!.task_score!);
                    return (
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          gap: 8,
                          padding: "16px 24px",
                          borderRadius: 6,
                          background: grade.bg,
                          border: `1px solid ${grade.border}`,
                        }}
                      >
                        <div
                          style={{
                            width: 36,
                            height: 36,
                            borderRadius: "50%",
                            border: `1.5px solid ${grade.border}`,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            flexShrink: 0,
                          }}
                        >
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: grade.text }}>
                            <path d="M8 21h8M12 17v4M7 4h10v4a5 5 0 0 1-10 0V4Z" strokeLinecap="round" strokeLinejoin="round" />
                            <path d="M7 5H4a1 1 0 0 0-1 1v1a4 4 0 0 0 4 4M17 5h3a1 1 0 0 1 1 1v1a4 4 0 0 1-4 4" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        </div>
                        <div style={{ textAlign: "center" }}>
                          <p style={{ margin: 0, fontSize: "var(--font-size-xs)", fontWeight: 700, letterSpacing: "0.08em", color: "var(--color-text-muted)", textTransform: "uppercase", display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
                            Task Score{" "}
                            <ScoreBreakdownTooltip
                              tables={section.latest_report!.score_breakdown.filter((t) => t.section === "task_report")}
                            />
                          </p>
                          <p style={{ margin: 0, fontSize: "1.5rem", fontWeight: 700, color: grade.text }}>{section.latest_report!.task_score}%</p>
                        </div>
                      </div>
                    );
                  })()}
                  {hasScore && section.latest_report!.file_name && (
                    <p
                      title={section.latest_report!.file_name}
                      style={{
                        margin: "6px 0 0",
                        fontSize: "var(--font-size-sm)",
                        color: "var(--color-text-faint)",
                        textAlign: "center",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        // maxWidth caps the filename independently — without it, a long name grows this whole column instead of ellipsis engaging.
                        maxWidth: 180,
                        marginLeft: "auto",
                        marginRight: "auto",
                      }}
                    >
                      {section.latest_report!.file_name}
                    </p>
                  )}
                </div>
              </div>

              {section.can_upload && section.next_upload_is_final && (
                <div style={{ padding: "0 16px 12px" }}>
                  <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-warning-text)" }}>
                    All recommendations were rejected — the next report you upload will be accepted as final, with no further review.
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {scoring && <ScoringDialog reason={scoring} />}
    </div>
  );
}