import { useEffect, useState, type ReactElement } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  decideRcCapaRecommendation,
  getProblemStatementRecord,
  getRcCapaCritique,
  getRcCapaHistory,
  pushRcCapaToSitReview,
  uploadRcCapaCritiqueReport,
  type RcCapaCritique,
  type RcCapaRecommendation,
  type RcCapaReport,
  type RcCapaState,
} from "../api/dashboard";
import { ApiError } from "../api/client";
import { DbErrorModal } from "../components/DbErrorModal";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FileDropzone } from "../components/FileDropzone";
import { RcConclusionGuidelines, CapaProposalGuidelines } from "../components/RcCapaGuidelines";
import { ScoreBreakdownTooltip } from "../components/ScoreBreakdownTooltip";
import { BoldText } from "../components/BoldText";
import { scoreGrade } from "../utils/scoreGrade";
import { ScoringDialog, type ScoringReason } from "../components/ScoringDialog";
import { RcCapaHistoryPanel } from "../components/RcCapaHistoryPanel";
import exportIcon from "../assets/icons/rci-export-icon.svg";
import "./RecordModulePage.css";

const CATEGORY_LABEL: Record<RcCapaCritique["category"], string> = {
  rc_impact: "Root Cause & Impact Assessment Critique",
  capa: "CAPA Critique",
};

const CATEGORY_GUIDELINES: Record<RcCapaCritique["category"], () => ReactElement> = {
  rc_impact: RcConclusionGuidelines,
  capa: CapaProposalGuidelines,
};

function formatDdMmYyyy(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${d.getFullYear()}`;
}

export function RcCapaCritiquePage() {
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [state, setState] = useState<RcCapaState | null>(null);
  const [problemStatement, setProblemStatement] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [reasonDrafts, setReasonDrafts] = useState<Record<number, string>>({});
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  const [showConfirm, setShowConfirm] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [pushError, setPushError] = useState<string | null>(null);
  const [scoring, setScoring] = useState<ScoringReason | null>(null);

  const [showHistory, setShowHistory] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyReports, setHistoryReports] = useState<RcCapaReport[]>([]);

  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    setLoading(true);
    setDbError(null);
    (async () => {
      try {
        const [data, psRecord] = await Promise.all([getRcCapaCritique(recordId), getProblemStatementRecord(recordId)]);
        if (cancelled) return;
        setState(data);
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

  if (!state) {
    return (
      <div className="empty-state">
        <p>Complete the earlier steps first — RC & CAPA Critique needs this investigation's record to exist.</p>
        <button type="button" className="btn-primary" onClick={() => navigate(`/records/${recordId}/task-critique`)}>
          Go to Task Critique
        </button>
      </div>
    );
  }

  async function handleUpload(file: File) {
    setUploading(true);
    setUploadError(null);
    // Predicted client-side from the state as of this click — a gospel
    // upload or the 3rd/final attempt both lock and get scored synchronously
    // as part of this same request (2026-08-18, per the user).
    if (state!.next_upload_is_final) {
      setScoring("gospel");
    } else if (state!.upload_count + 1 >= state!.max_uploads) {
      setScoring("final_attempt");
    }
    try {
      const updated = await uploadRcCapaCritiqueReport(recordId!, file);
      setState(updated);
    } catch (err) {
      setUploadError(err instanceof ApiError ? String(err.detail) : "Failed to critique the uploaded report");
    } finally {
      setUploading(false);
      setScoring(null);
    }
  }

  async function handleAccept(recommendationId: number) {
    setDecisionBusy(true);
    setDecisionError(null);
    try {
      const updated = await decideRcCapaRecommendation(recordId!, recommendationId, "accepted");
      setState(updated);
    } catch (err) {
      setDecisionError(err instanceof ApiError ? String(err.detail) : "Failed to accept recommendation");
    } finally {
      setDecisionBusy(false);
    }
  }

  async function handleReject(recommendationId: number) {
    const reason = (reasonDrafts[recommendationId] ?? "").trim();
    if (!reason) return;
    setDecisionBusy(true);
    setDecisionError(null);
    // Rejecting the LAST still-pending recommendation across BOTH categories
    // (rc_impact + capa combined — see db/critique_state.py, which flattens
    // them before applying its all-rejected rule), where every other one is
    // already rejected too, immediately locks and scores this report.
    // Predicted client-side from the state as of this click.
    const allRecs = state!.latest_report!.critiques.flatMap((c) => c.recommendations);
    if (allRecs.filter((r) => r.id !== recommendationId).every((r) => r.decision === "rejected")) {
      setScoring("all_decided");
    }
    try {
      const updated = await decideRcCapaRecommendation(recordId!, recommendationId, "rejected", reason);
      setState(updated);
      setRejectingId(null);
    } catch (err) {
      setDecisionError(err instanceof ApiError ? String(err.detail) : "Failed to reject recommendation");
    } finally {
      setDecisionBusy(false);
      setScoring(null);
    }
  }

  function handleOpenHistory() {
    setShowHistory(true);
    setHistoryLoading(true);
    getRcCapaHistory(recordId!)
      .then(setHistoryReports)
      .finally(() => setHistoryLoading(false));
  }

  async function handlePushToSitReview() {
    setShowConfirm(false);
    setPushBusy(true);
    setPushError(null);
    try {
      const updated = await pushRcCapaToSitReview(recordId!);
      setState(updated);
      navigate(`/records/${recordId}/rci-report`);
    } catch (err) {
      setPushError(err instanceof ApiError ? String(err.detail) : "Failed to push for SIT review");
    } finally {
      setPushBusy(false);
    }
  }

  function renderRecommendationCard(rec: RcCapaRecommendation) {
    const isRejecting = rejectingId === rec.id;
    return (
      <div key={rec.id} style={{ border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 13, display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ flex: 1, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>{rec.description}</span>
          {rec.decision === "pending" && !isRejecting && (
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" className="btn-outline" disabled={decisionBusy} onClick={() => handleAccept(rec.id)} style={{ color: "var(--color-success-text)", borderColor: "var(--color-success-text)" }}>
                Accept
              </button>
              <button
                type="button"
                className="btn-outline"
                disabled={decisionBusy}
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
                disabled={decisionBusy || !(reasonDrafts[rec.id] ?? "").trim()}
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
  }

  const report = state.latest_report;
  const isComplete = state.status === "complete";
  const waitingForSitReview = state.sit_review_status === "pending";

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
        <p className="card-title">RC & CAPA Critique</p>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button type="button" className="btn-outline" onClick={handleOpenHistory}>
            Recommendation History
          </button>
          {waitingForSitReview ? (
            <button type="button" className="btn-outline" disabled style={{ cursor: "default" }}>
              Waiting for SIT Review
            </button>
          ) : (
            <button
              type="button"
              className="btn-primary"
              style={{ display: "flex", alignItems: "center", gap: 10, opacity: isComplete ? 1 : 0.4, cursor: isComplete ? "pointer" : "default" }}
              disabled={!isComplete || pushBusy}
              onClick={() => setShowConfirm(true)}
            >
              <img src={exportIcon} alt="" width={16} height={16} />
              Accept and Push for SIT Lead Review
            </button>
          )}
        </div>
      </div>

      {pushError && <p className="error-banner">{pushError}</p>}

      {isComplete && (
        <div className="card" style={{ alignItems: "center", textAlign: "center", gap: 16, borderTop: "4px solid var(--color-success-text)" }}>
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: "50%",
              border: "2px solid var(--color-success-text)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="var(--color-success-text)" strokeWidth="2.5">
              <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <p style={{ margin: 0, fontWeight: 700, fontSize: "var(--font-size-lg)" }}>Root Cause, Impact Assessment & CAPA Critique Complete!</p>
            <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
              All observations have been resolved and the RC & CAPA Critique is fully completed.
              {waitingForSitReview ? " Waiting for SIT Review." : ""}
            </p>
          </div>

          {report?.total_score != null && (() => {
            const grade = scoreGrade(report.total_score);
            return (
              <div
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 12,
                  padding: 16,
                  borderRadius: 8,
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
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={grade.text} strokeWidth="2">
                    <path d="M8 21h8M12 17v4M7 4h10v4a5 5 0 0 1-10 0V4Z" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M7 5H4a1 1 0 0 0-1 1v1a4 4 0 0 0 4 4M17 5h3a1 1 0 0 1 1 1v1a4 4 0 0 1-4 4" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <div style={{ textAlign: "center" }}>
                  <p style={{ margin: 0, fontSize: "var(--font-size-xs)", fontWeight: 600, letterSpacing: "0.05em", color: "var(--color-text-muted)", display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
                    RC & CAPA CRITIQUE SCORE{" "}
                    <ScoreBreakdownTooltip
                      tables={report.score_breakdown}
                      description="This is the cumulative score from the RC, Impact, and CAPA scores — not an independently scored section of its own."
                      hideTables
                    />
                  </p>
                  <p style={{ margin: 0, fontSize: "1.5rem", fontWeight: 700, color: grade.text }}>{report.total_score}%</p>
                </div>
              </div>
            );
          })()}

          {report && (report.rc_score != null || report.impact_score != null || report.capa_score != null) && (
            <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 12 }}>
              {[
                { label: "RC CRITIQUE SCORE", value: report.rc_score, sections: ["rc"] },
                { label: "IMPACT CRITIQUE SCORE", value: report.impact_score, sections: ["impact"] },
                { label: "CAPA CRITIQUE SCORE", value: report.capa_score, sections: ["capa"] },
              ]
                .filter((s) => s.value != null)
                .map((s) => {
                  const grade = scoreGrade(s.value!);
                  return (
                    <div
                      key={s.label}
                      style={{
                        width: "100%",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 12,
                        padding: 13,
                        borderRadius: 8,
                        background: grade.bg,
                        border: `1px solid ${grade.border}`,
                      }}
                    >
                      <div
                        style={{
                          width: 32,
                          height: 32,
                          borderRadius: "50%",
                          border: `1.5px solid ${grade.border}`,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          flexShrink: 0,
                        }}
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={grade.text} strokeWidth="2">
                          <path d="M8 21h8M12 17v4M7 4h10v4a5 5 0 0 1-10 0V4Z" strokeLinecap="round" strokeLinejoin="round" />
                          <path d="M7 5H4a1 1 0 0 0-1 1v1a4 4 0 0 0 4 4M17 5h3a1 1 0 0 1 1 1v1a4 4 0 0 1-4 4" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </div>
                      <div style={{ textAlign: "center" }}>
                        <p style={{ margin: 0, fontSize: "var(--font-size-xs)", fontWeight: 600, letterSpacing: "0.05em", color: "var(--color-text-muted)", display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
                          {s.label} <ScoreBreakdownTooltip tables={report.score_breakdown.filter((t) => s.sections.includes(t.section))} />
                        </p>
                        <p style={{ margin: 0, fontSize: "1.25rem", fontWeight: 700, color: grade.text }}>{s.value}%</p>
                      </div>
                    </div>
                  );
                })}
            </div>
          )}

          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
            {state.due_date && (
              <span style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "6px 12px", fontSize: "var(--font-size-sm)", fontWeight: 700 }}>
                TCD: {state.due_date}
              </span>
            )}
            {report && (
              <span style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "6px 12px", fontSize: "var(--font-size-sm)", fontWeight: 700 }}>
                Completed On: {formatDdMmYyyy(report.uploaded_at)}
              </span>
            )}
            <span style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "6px 12px", fontSize: "var(--font-size-sm)", fontWeight: 700 }}>
              Record: {recordId}
            </span>
            {state.investigator && (
              <span style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "6px 12px", fontSize: "var(--font-size-sm)", fontWeight: 700 }}>
                Investigator: {state.investigator}
              </span>
            )}
          </div>
        </div>
      )}

      {state.next_upload_is_final && state.can_upload && (
        <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-warning-text)" }}>
          All recommendations were rejected — the next report you upload will be accepted as final, with no further review.
        </p>
      )}

      {state.can_upload && (
        <div className="card" style={{ gap: 12 }}>
          <p className="card-title">{state.upload_count === 0 ? "Upload Report" : "Upload Updated RC & CAPA Critique"}</p>
          <FileDropzone
            disabled={uploading}
            loading={uploading}
            onFileSelected={(file) => {
              setUploadError(null);
              handleUpload(file);
            }}
          />
          {uploadError && (
            <p
              className="error-banner"
              title={uploadError}
              style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {uploadError}
            </p>
          )}
        </div>
      )}

      {decisionError && <p className="error-banner">{decisionError}</p>}

      {report && !report.is_gospel && report.critiques.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {report.critiques.map((critique) => {
            const CategoryGuidelines = CATEGORY_GUIDELINES[critique.category];
            return (
            <div key={critique.category} style={{ border: "1px solid var(--color-card-border)", borderRadius: 10, overflow: "hidden" }}>
              <div style={{ background: "var(--color-bg)", borderBottom: "1px solid var(--color-card-border)", padding: "16px 24px" }}>
                <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-base)" }}>
                  {CATEGORY_LABEL[critique.category]} <CategoryGuidelines />
                </p>
              </div>
              <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                {critique.summary ? (
                  <div style={{ background: "var(--color-success-bg)", border: "1px solid var(--color-card-border)", borderRadius: 10, padding: "13px 17px" }}>
                    <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-base)" }}>Summary Of the Report</p>
                    <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}><BoldText text={critique.summary} /></p>
                  </div>
                ) : (
                  <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>Critique pending.</p>
                )}

                {!isComplete && critique.recommendations.length > 0 && (
                  critique.category === "rc_impact" ? (
                    <>
                      {(() => {
                        const rootCauseRecs = critique.recommendations.filter((r) => r.type !== "impact");
                        const impactRecs = critique.recommendations.filter((r) => r.type === "impact");
                        return (
                          <>
                            {rootCauseRecs.length > 0 && (
                              <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-card-border)", borderRadius: 10, padding: "13px 17px", display: "flex", flexDirection: "column", gap: 8 }}>
                                <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-base)" }}>Root Cause</p>
                                {rootCauseRecs.map(renderRecommendationCard)}
                              </div>
                            )}
                            {impactRecs.length > 0 && (
                              <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-card-border)", borderRadius: 10, padding: "13px 17px", display: "flex", flexDirection: "column", gap: 8 }}>
                                <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-base)" }}>Impact Assessment</p>
                                {impactRecs.map(renderRecommendationCard)}
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </>
                  ) : (
                    <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-card-border)", borderRadius: 10, padding: "13px 17px", display: "flex", flexDirection: "column", gap: 8 }}>
                      <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-base)" }}>Recommendations for Improvements</p>
                      {critique.recommendations.map(renderRecommendationCard)}
                    </div>
                  )
                )}
              </div>
            </div>
            );
          })}
        </div>
      )}

      {report?.is_gospel && (
        <div className="card">
          <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
            This report was accepted as final — no recommendations were generated for it.
          </p>
        </div>
      )}

      {showConfirm && (
        <ConfirmDialog
          title="Accept RCI & CAPA Critique?"
          message="Are you sure you want to accept and push the RC & CAPA Critique for SIT Review?"
          onCancel={() => setShowConfirm(false)}
          onConfirm={handlePushToSitReview}
        />
      )}

      {scoring && <ScoringDialog reason={scoring} />}

      {showHistory && (
        <RcCapaHistoryPanel reports={historyReports} loading={historyLoading} onClose={() => setShowHistory(false)} />
      )}
    </div>
  );
}