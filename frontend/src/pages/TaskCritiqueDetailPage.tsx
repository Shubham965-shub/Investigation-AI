import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  decideTaskCritiqueRecommendation,
  getTaskCritique,
  uploadTaskCritiqueReport,
  type TaskCritiqueSection,
} from "../api/dashboard";
import { ApiError } from "../api/client";
import { DbErrorModal } from "../components/DbErrorModal";
import { FileDropzone } from "../components/FileDropzone";
import investigatorIcon from "../assets/icons/rci-person-investigator.svg";
import rowChevronIcon from "../assets/icons/rci-row-chevron.svg";
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

  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [reasonDrafts, setReasonDrafts] = useState<Record<number, string>>({});

  useEffect(() => {
    if (!recordId || Number.isNaN(taskIndex)) return;
    let cancelled = false;
    setLoading(true);
    setDbError(null);
    (async () => {
      try {
        const data = await getTaskCritique(recordId);
        if (cancelled) return;
        const found = data?.sections.find((s) => s.task_index === taskIndex) ?? null;
        setSection(found);
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
    } catch (err) {
      setActionError(err instanceof ApiError ? String(err.detail) : "Failed to upload report");
    } finally {
      setBusy(false);
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
    try {
      const updated = await decideTaskCritiqueRecommendation(recordId!, taskIndex, recommendationId, "rejected", reason);
      setSection(updated);
      setRejectingId(null);
    } catch (err) {
      setActionError(err instanceof ApiError ? String(err.detail) : "Failed to reject recommendation");
    } finally {
      setBusy(false);
    }
  }

  const report = section.latest_report;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card" style={{ gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ fontWeight: 600, fontSize: "var(--font-size-base)" }}>{section.title}</span>
              <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                ({section.task_count} {section.task_count === 1 ? "task" : "tasks"})
              </span>
            </div>
            {section.correlation && (
              <p style={{ margin: "2px 0 0", fontSize: "var(--font-size-base)", color: "var(--color-text-faint)" }}>{section.correlation}</p>
            )}
          </div>
          <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", fontSize: "var(--font-size-md)", color: "var(--color-text-faint)", minWidth: 160, boxSizing: "border-box" }}>
            TCD: {section.due_date || "—"}
          </div>
          <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", display: "flex", alignItems: "center", gap: 6, minWidth: 140, boxSizing: "border-box" }}>
            <img src={investigatorIcon} alt="" width={16} height={16} />
            <span style={{ fontSize: "var(--font-size-md)", color: "var(--color-text-faint)" }}>{section.assignee || "Unassigned"}</span>
          </div>
          <span className={`status-pill ${section.status}`}>{STATUS_LABEL[section.status]}</span>
          <button
            type="button"
            onClick={() => navigate(`/records/${recordId}/task-critique`)}
            style={{ background: "none", border: "none" }}
            aria-label="Back to Task Critique History"
          >
            <img src={rowChevronIcon} alt="" width={24} height={24} />
          </button>
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

                {report.recommendations.length > 0 && (
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
        </div>
      </div>
    </div>
  );
}