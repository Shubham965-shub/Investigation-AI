import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  decideTaskCritiqueRecommendation,
  getTaskCritique,
  getTaskCritiqueHistory,
  uploadTaskCritiqueReport,
  type RecommendationHistoryAttempt,
  type TaskCritiqueSection,
} from "../api/dashboard";
import { ApiError } from "../api/client";
import { DbErrorModal } from "../components/DbErrorModal";
import { FileDropzone } from "../components/FileDropzone";
import { ScoringDialog, type ScoringReason } from "../components/ScoringDialog";
import { formatAttemptTimestamp } from "../utils/formatTimestamp";
import investigatorIcon from "../assets/icons/rci-person-investigator.svg";
import backChevronIcon from "../assets/icons/back-chevron.svg";
import "./RecordModulePage.css";

const STATUS_LABEL: Record<TaskCritiqueSection["status"], string> = {
  pending: "Pending",
  in_progress: "In Progress",
  complete: "Complete",
};

export function TaskCritiqueDetailPage() {
  const { recordId, taskIndex: taskIndexParam } = useParams<{ recordId: string; taskIndex: string }>();
  const navigate = useNavigate();
  const taskIndex = Number(taskIndexParam);

  const [loading, setLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [section, setSection] = useState<TaskCritiqueSection | null | undefined>(undefined);
  // Same 1-based numbering as the main Task Critique list (index + 1 within
  // the sections array, not the task_index route param) — carried forward
  // here so a task's number stays consistent between the two pages
  // (2026-08-14, per the user).
  const [sectionNumber, setSectionNumber] = useState<number | null>(null);

  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [reasonDrafts, setReasonDrafts] = useState<Record<number, string>>({});
  const [scoring, setScoring] = useState<ScoringReason | null>(null);
  const [history, setHistory] = useState<RecommendationHistoryAttempt[]>([]);

  useEffect(() => {
    if (!recordId || Number.isNaN(taskIndex)) return;
    let cancelled = false;
    setLoading(true);
    setDbError(null);
    (async () => {
      try {
        const [data, historyData] = await Promise.all([getTaskCritique(recordId), getTaskCritiqueHistory(recordId, taskIndex)]);
        if (cancelled) return;
        const foundIndex = data?.sections.findIndex((s) => s.task_index === taskIndex) ?? -1;
        setSection(foundIndex >= 0 ? data!.sections[foundIndex] : null);
        setSectionNumber(foundIndex >= 0 ? foundIndex + 1 : null);
        setHistory(historyData);
      } catch (err) {
        if (!cancelled) setDbError(err instanceof ApiError ? String(err.detail) : "Could not reach the database.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [recordId, taskIndex, retryKey]);

  if (!recordId || Number.isNaN(taskIndex)) return null;

  if (loading) {
    return (
      <div className="card">
        <p className="card-title">Loading task…</p>
      </div>
    );
  }

  if (dbError) {
    return <DbErrorModal message={dbError} onRetry={() => setRetryKey((k) => k + 1)} />;
  }

  if (!section) {
    return (
      <div className="empty-state">
        <p>This task could not be found.</p>
        <div className="footer-actions">
          <button type="button" className="btn-outline" onClick={() => navigate(`/records/${recordId}/task-critique`)}>
            Back to Task Critique History
          </button>
        </div>
      </div>
    );
  }

  async function handleUpload(file: File) {
    setBusy(true);
    setActionError("");
    // Predicted client-side from the state as of this click — a gospel
    // upload (all recs previously rejected) or the 3rd/final attempt both
    // lock and get scored synchronously as part of this same request
    // (2026-08-18, per the user: show that scoring is under way, correctly
    // reflecting which of the two no-decision-needed cases this is).
    if (section!.next_upload_is_final) {
      setScoring("gospel");
    } else if (section!.upload_count + 1 >= section!.max_uploads) {
      setScoring("final_attempt");
    }
    try {
      const updated = await uploadTaskCritiqueReport(recordId!, taskIndex, file);
      if (updated.locked) {
        // Final upload (gospel or 3rd attempt) — scored, nothing left to
        // review, so go back to the main list page instead of showing this
        // task's (now closed) detail page.
        navigate(`/records/${recordId}/task-critique`);
        return;
      }
      setSection(updated);
      // This upload just added a new attempt to the audit trail.
      getTaskCritiqueHistory(recordId!, taskIndex).then(setHistory);
    } catch (err) {
      setActionError(err instanceof ApiError ? String(err.detail) : "Failed to upload report");
    } finally {
      setBusy(false);
      setScoring(null);
    }
  }

  async function handleAccept(recommendationId: number) {
    setBusy(true);
    setActionError("");
    try {
      const updated = await decideTaskCritiqueRecommendation(recordId!, taskIndex, recommendationId, "accepted");
      setSection(updated);
    } catch (err) {
      setActionError(err instanceof ApiError ? String(err.detail) : "Failed to accept recommendation");
    } finally {
      setBusy(false);
    }
  }

  async function handleReject(recommendationId: number) {
    const reason = (reasonDrafts[recommendationId] ?? "").trim();
    if (!reason) return;
    setBusy(true);
    setActionError("");
    // Rejecting the LAST still-pending recommendation, where every other one
    // is already rejected too, immediately locks and scores this report (see
    // db/critique_state.py's all-rejected branch) — predicted client-side
    // from the state as of this click, not assumed from the response, so the
    // dialog can appear the instant the request goes out.
    if (report!.recommendations.filter((r) => r.id !== recommendationId).every((r) => r.decision === "rejected")) {
      setScoring("all_decided");
    }
    try {
      const updated = await decideTaskCritiqueRecommendation(recordId!, taskIndex, recommendationId, "rejected", reason);
      setSection(updated);
      setRejectingId(null);
    } catch (err) {
      setActionError(err instanceof ApiError ? String(err.detail) : "Failed to reject recommendation");
    } finally {
      setScoring(null);
      setBusy(false);
    }
  }

  const report = section.latest_report;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card" style={{ gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <button
            type="button"
            onClick={() => navigate(`/records/${recordId}/task-critique`)}
            style={{ background: "none", border: "none" }}
            aria-label="Back to Task Critique History"
          >
            <img src={backChevronIcon} alt="" width={24} height={24} />
          </button>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ fontWeight: 600, fontSize: "var(--font-size-base)" }}>
                {sectionNumber != null ? `${sectionNumber}. ` : ""}
                {section.title}
              </span>
              <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                ({section.task_count} {section.task_count === 1 ? "task" : "tasks"})
              </span>
            </div>
            {section.correlation && (
              <p style={{ margin: "2px 0 0", fontSize: "var(--font-size-base)", color: "var(--color-text-faint)" }}>{section.correlation}</p>
            )}
          </div>
          {section.latest_report && (
            <>
              <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", fontSize: "var(--font-size-md)", color: "var(--color-text-faint)", minWidth: 160, boxSizing: "border-box" }}>
                TCD: {section.due_date || "—"}
              </div>
              <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", display: "flex", alignItems: "center", gap: 6, minWidth: 140, boxSizing: "border-box" }}>
                <img src={investigatorIcon} alt="" width={16} height={16} />
                <span style={{ fontSize: "var(--font-size-md)", color: "var(--color-text-faint)" }}>{section.assignee || "Unassigned"}</span>
              </div>
            </>
          )}
          <span className={`status-pill ${section.status}`}>{STATUS_LABEL[section.status]}</span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {section.next_upload_is_final && section.can_upload && (
            <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-warning-text)" }}>
              All recommendations were rejected — the next report you upload will be accepted as final, with no further review.
            </p>
          )}

          {section.can_upload && (
            <FileDropzone
              disabled={busy}
              loading={busy}
              label={section.upload_count === 0 ? "Drag & Drop or Choose file to upload" : "Drag & Drop or Choose an updated report to upload"}
              onFileSelected={handleUpload}
            />
          )}

          {actionError && <p className="error-banner">{actionError}</p>}

          {report && (
            <div style={{ border: "1px solid var(--color-card-border)", borderRadius: 10, overflow: "hidden" }}>
              <div style={{ background: "var(--color-bg)", borderBottom: "1px solid var(--color-card-border)", padding: "16px 24px" }}>
                <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-base)" }}>Observations</p>
              </div>
              <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                {report.is_gospel ? (
                  <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
                    This report was accepted as final — no recommendations were generated for it.
                  </p>
                ) : report.summary ? (
                  <div style={{ background: "var(--color-success-bg)", border: "1px solid var(--color-card-border)", borderRadius: 10, padding: "13px 17px" }}>
                    <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-base)" }}>Summary Of the Report</p>
                    <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>{report.summary}</p>
                  </div>
                ) : (
                  <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
                    Critique pending — the report has been uploaded and is awaiting AI review.
                  </p>
                )}

                {!section.locked && report.recommendations.length > 0 && (
                  <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-card-border)", borderRadius: 10, padding: "13px 17px", display: "flex", flexDirection: "column", gap: 8 }}>
                    <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-base)" }}>Recommendations for Improvements</p>
                    {report.recommendations.map((rec) => {
                      const isRejecting = rejectingId === rec.id;
                      return (
                        <div key={rec.id} style={{ border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 13, display: "flex", flexDirection: "column", gap: 8 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ flex: 1, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>{rec.description}</span>
                            {rec.decision === "pending" && !isRejecting && (
                              <div style={{ display: "flex", gap: 8 }}>
                                <button type="button" className="btn-outline" disabled={busy} onClick={() => handleAccept(rec.id)} style={{ color: "var(--color-success-text)", borderColor: "var(--color-success-text)" }}>
                                  Accept
                                </button>
                                <button
                                  type="button"
                                  className="btn-outline"
                                  disabled={busy}
                                  onClick={() => setRejectingId(rec.id)}
                                  style={{ color: "var(--color-danger-text)", borderColor: "var(--color-danger-text)" }}
                                >
                                  Reject
                                </button>
                              </div>
                            )}
                            {rec.decision === "accepted" && <span className="status-pill complete">Accepted</span>}
                            {rec.decision === "rejected" && <span className="status-pill" style={{ color: "var(--color-danger-text)", borderColor: "var(--color-danger-text)" }}>Rejected</span>}
                          </div>
                          {isRejecting && (
                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                              <label style={{ fontSize: "var(--font-size-sm)", fontWeight: 600, color: "var(--color-text-muted)" }}>Reason *</label>
                              <div style={{ display: "flex", gap: 8 }}>
                                <input
                                  type="text"
                                  className="field-value"
                                  placeholder="Rejection reason"
                                  value={reasonDrafts[rec.id] ?? ""}
                                  onChange={(e) => setReasonDrafts((prev) => ({ ...prev, [rec.id]: e.target.value }))}
                                  style={{ flex: 1, height: "auto" }}
                                />
                                <button
                                  type="button"
                                  className="btn-outline"
                                  disabled={busy || !(reasonDrafts[rec.id] ?? "").trim()}
                                  onClick={() => handleReject(rec.id)}
                                  style={{ color: "var(--color-danger-text)", borderColor: "var(--color-danger-text)" }}
                                >
                                  Confirm Reject
                                </button>
                              </div>
                            </div>
                          )}
                          {rec.decision === "rejected" && rec.reason && (
                            <p style={{ margin: 0, fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>Reason: {rec.reason}</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Full history across every attempt — independent of lock/complete
              state, so it stays visible even once the task is scored and
              done (2026-08-18, per the user). */}
          {history.length > 0 && (
            <div style={{ border: "1px solid var(--color-card-border)", borderRadius: 10, overflow: "hidden" }}>
              <div style={{ background: "var(--color-bg)", borderBottom: "1px solid var(--color-card-border)", padding: "16px 24px" }}>
                <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-base)" }}>Recommendation History</p>
              </div>
              <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                {history.map((attempt) => (
                  <div key={attempt.attempt_number} style={{ border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 13, display: "flex", flexDirection: "column", gap: 6 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: 600, fontSize: "var(--font-size-sm)" }}>Attempt {attempt.attempt_number}</span>
                      <span style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
                        {formatAttemptTimestamp(attempt.created_at)}
                      </span>
                    </div>
                    {attempt.summary && (
                      <p style={{ margin: 0, fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>{attempt.summary}</p>
                    )}
                    {attempt.recommendations.length > 0 && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {attempt.recommendations.map((rec) => (
                          <div key={rec.id} style={{ border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 13, display: "flex", flexDirection: "column", gap: 8 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span style={{ flex: 1, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>{rec.description}</span>
                              {/* Read-only mirror of the live section's Accept/Reject
                                  pills — both options always shown, the actual
                                  decision highlighted and the other dimmed
                                  (2026-08-18, per the user), instead of buttons. */}
                              <div style={{ display: "flex", gap: 8 }}>
                                <span
                                  className={rec.decision === "accepted" ? "status-pill complete" : undefined}
                                  style={rec.decision === "accepted" ? undefined : { fontSize: "var(--font-size-sm)", color: "var(--color-text-faint)", opacity: 0.5 }}
                                >
                                  Accepted
                                </span>
                                <span
                                  className={rec.decision === "rejected" ? "status-pill" : undefined}
                                  style={
                                    rec.decision === "rejected"
                                      ? { color: "var(--color-danger-text)", borderColor: "var(--color-danger-text)" }
                                      : { fontSize: "var(--font-size-sm)", color: "var(--color-text-faint)", opacity: 0.5 }
                                  }
                                >
                                  Rejected
                                </span>
                              </div>
                            </div>
                            {rec.decision === "rejected" && rec.reason && (
                              <p style={{ margin: 0, fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>Reason: {rec.reason}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {scoring && <ScoringDialog reason={scoring} />}
    </div>
  );
}