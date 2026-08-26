import { useEffect, useRef, useState, type ReactElement } from "react";
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
import { IncorporateChangesDialog } from "../components/IncorporateChangesDialog";
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

// The RC/Impact/CAPA drilldown behind the completion screen's "Score
// Details" button (2026-08-26, per the user) — same 3 score rows that used
// to sit inline on the completion card, just moved into a dialog.
function ScoreDetailsDialog({ report, onClose }: { report: RcCapaReport; onClose: () => void }) {
  const rows = [
    { label: "RC CRITIQUE SCORE", value: report.rc_score, sections: ["rc"] },
    { label: "IMPACT CRITIQUE SCORE", value: report.impact_score, sections: ["impact"] },
    { label: "CAPA CRITIQUE SCORE", value: report.capa_score, sections: ["capa"] },
  ].filter((s) => s.value != null);

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(73, 84, 80, 0.45)", zIndex: 60 }} />
      <div
        role="dialog"
        aria-modal="true"
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          background: "var(--color-surface)",
          borderRadius: 10,
          width: "min(480px, 92vw)",
          padding: 24,
          zIndex: 61,
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <p style={{ margin: 0, fontWeight: 700, fontSize: "var(--font-size-base)" }}>Score Details</p>
          <button type="button" onClick={onClose} aria-label="Close" style={{ background: "none", border: "none", cursor: "pointer", fontSize: "var(--font-size-lg)", lineHeight: 1, color: "var(--color-text-muted)" }}>
            ×
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {rows.map((s) => {
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
      </div>
    </>
  );
}

// One self-contained blanket accept/reject block per recommendation
// subsection (Root Cause / Impact Assessment / CAPA's own "Recommendations
// for Improvements") — mirrors Task Critique's single-section version
// (2026-08-26, per the user: "do the same in rc and capa critique"), just
// instantiated once per subsection here since this page has three instead
// of one. Checkboxes + local bulk/deselect state live per-group (ids never
// collide across groups since they're real DB row ids); the actual decision
// calls and the "does this lock the whole report" prediction go through the
// parent, since that prediction needs every recommendation across BOTH
// critique categories, not just this group's own.
function RecommendationGroup({
  recs,
  allRecsFlat,
  decisionBusy,
  decide,
  onDecided,
  setDecisionBusy,
  setDecisionError,
  setScoring,
}: {
  recs: RcCapaRecommendation[];
  allRecsFlat: RcCapaRecommendation[];
  decisionBusy: boolean;
  decide: (recommendationId: number, decision: "accepted" | "rejected", reason?: string) => Promise<RcCapaState>;
  onDecided: (updated: RcCapaState) => void;
  setDecisionBusy: (busy: boolean) => void;
  setDecisionError: (err: string | null) => void;
  setScoring: (reason: ScoringReason | null) => void;
}) {
  const [uncheckedIds, setUncheckedIds] = useState<Set<number>>(new Set());
  const [deselectPrompt, setDeselectPrompt] = useState(false);
  // A separate reason per deselected recommendation (2026-08-26, per the
  // user — previously one shared reason covered every deselected
  // recommendation; now each gets its own labeled box in a table). Keyed by
  // recommendation id.
  const [deselectReasons, setDeselectReasons] = useState<Record<number, string>>({});

  const pending = recs.filter((r) => r.decision === "pending");

  function toggleChecked(id: number) {
    setUncheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // Every recommendation NOT in this batch must already be rejected for the
  // batch's rejections to result in the whole report having nothing but
  // rejected recommendations left — same rule the page previously applied
  // per single recommendation, generalized to a batch.
  function wouldLockEverything(batchIds: number[]): boolean {
    return allRecsFlat.filter((r) => !batchIds.includes(r.id)).every((r) => r.decision === "rejected");
  }

  async function acceptAll(ids: number[]) {
    if (ids.length === 0) return;
    setDecisionBusy(true);
    setDecisionError(null);
    try {
      let updated: RcCapaState | undefined;
      for (const id of ids) {
        updated = await decide(id, "accepted");
      }
      if (updated) onDecided(updated);
    } catch (err) {
      setDecisionError(err instanceof ApiError ? String(err.detail) : "Failed to accept recommendations");
    } finally {
      setDecisionBusy(false);
    }
  }

  function handleYesClick() {
    const hasDeselected = pending.some((r) => uncheckedIds.has(r.id));
    if (!hasDeselected) {
      acceptAll(pending.map((r) => r.id));
      return;
    }
    setDeselectPrompt(true);
  }

  async function handlePartialAccept() {
    const toAccept = pending.filter((r) => !uncheckedIds.has(r.id));
    const toReject = pending.filter((r) => uncheckedIds.has(r.id));
    if (toReject.some((r) => !(deselectReasons[r.id] ?? "").trim())) return;
    // Closed immediately, not just on success (2026-08-26, per the user) —
    // ScoringDialog below renders at the same z-index the instant scoring
    // is predicted, and this dialog previously stayed mounted for the whole
    // (possibly long) scoring wait underneath/alongside it, looking like a
    // broken white overlay.
    setDeselectPrompt(false);
    setDecisionBusy(true);
    setDecisionError(null);
    if (toReject.length > 0 && wouldLockEverything(toReject.map((r) => r.id))) setScoring("all_decided");
    try {
      let updated: RcCapaState | undefined;
      for (const rec of toAccept) {
        updated = await decide(rec.id, "accepted");
      }
      for (const rec of toReject) {
        updated = await decide(rec.id, "rejected", deselectReasons[rec.id].trim());
      }
      if (updated) onDecided(updated);
      setDeselectReasons({});
      setUncheckedIds(new Set());
    } catch (err) {
      setDecisionError(err instanceof ApiError ? String(err.detail) : "Failed to record recommendation decisions");
    } finally {
      setScoring(null);
      setDecisionBusy(false);
    }
  }

  return (
    <>
      {pending.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: "var(--font-size-base)", fontWeight: 600 }}>Accept Recommendations?</span>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" className="btn-outline" disabled={decisionBusy} onClick={handleYesClick} style={{ color: "var(--color-success-text)", borderColor: "var(--color-success-text)" }}>
              Yes
            </button>
          </div>
        </div>
      )}

      {recs.map((rec, recIdx) => (
        <div key={rec.id} style={{ border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 13, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <input
              type="checkbox"
              checked={rec.decision === "pending" ? !uncheckedIds.has(rec.id) : rec.decision === "accepted"}
              disabled={rec.decision !== "pending" || decisionBusy}
              onChange={() => toggleChecked(rec.id)}
              style={{ marginTop: 3, cursor: rec.decision === "pending" ? "pointer" : "default" }}
            />
            <span style={{ flex: 1, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
              {recIdx + 1}. {rec.description}
            </span>
          </div>
          {rec.decision === "rejected" && rec.reason && (
            <p style={{ margin: 0, fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>Reason: {rec.reason}</p>
          )}
        </div>
      ))}

      {deselectPrompt && (
        <>
          <div onClick={() => setDeselectPrompt(false)} style={{ position: "fixed", inset: 0, background: "rgba(73, 84, 80, 0.45)", zIndex: 60 }} />
          <div
            role="alertdialog"
            aria-modal="true"
            style={{
              position: "fixed",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              background: "var(--color-surface)",
              borderRadius: 10,
              width: "min(560px, 92vw)",
              padding: 24,
              zIndex: 61,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <p style={{ margin: 0, fontWeight: 700, fontSize: "var(--font-size-base)" }}>Why were these recommendations deselected?</p>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--font-size-sm)" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "6px 8px", border: "1px solid var(--color-card-border)", background: "var(--color-bg)", width: "35%" }}>Recommendation</th>
                  <th style={{ textAlign: "left", padding: "6px 8px", border: "1px solid var(--color-card-border)", background: "var(--color-bg)" }}>Reason</th>
                </tr>
              </thead>
              <tbody>
                {recs
                  .map((r, i) => ({ r, num: i + 1 }))
                  .filter(({ r }) => r.decision === "pending" && uncheckedIds.has(r.id))
                  .map(({ r, num }, idx) => (
                    <tr key={r.id}>
                      <td style={{ padding: "6px 8px", border: "1px solid var(--color-card-border)", verticalAlign: "top" }}>
                        #{num}. {r.description}
                      </td>
                      <td style={{ padding: "6px 8px", border: "1px solid var(--color-card-border)" }}>
                        <input
                          type="text"
                          className="field-value"
                          placeholder="Reason"
                          value={deselectReasons[r.id] ?? ""}
                          onChange={(e) => setDeselectReasons((prev) => ({ ...prev, [r.id]: e.target.value }))}
                          style={{ height: "auto", width: "100%", boxSizing: "border-box" }}
                          autoFocus={idx === 0}
                        />
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
              <button type="button" className="btn-outline" onClick={() => { setDeselectPrompt(false); setDeselectReasons({}); }}>
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary"
                disabled={
                  decisionBusy ||
                  recs
                    .filter((r) => r.decision === "pending" && uncheckedIds.has(r.id))
                    .some((r) => !(deselectReasons[r.id] ?? "").trim())
                }
                onClick={handlePartialAccept}
              >
                Confirm
              </button>
            </div>
          </div>
        </>
      )}
    </>
  );
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

  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  const [showConfirm, setShowConfirm] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [pushError, setPushError] = useState<string | null>(null);
  const [scoring, setScoring] = useState<ScoringReason | null>(null);

  // The RC/Impact/CAPA score drilldown moved out of the always-visible
  // completion card into its own dialog behind a "Score Details" button
  // (2026-08-26, per the user) — the total score stays inline as before.
  const [showScoreDetails, setShowScoreDetails] = useState(false);

  const [showHistory, setShowHistory] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyReports, setHistoryReports] = useState<RcCapaReport[]>([]);

  // Fires once every recommendation on the current report has been decided
  // and a new upload becomes possible again — detected as can_upload's
  // false -> true transition (2026-08-26, per the user), rather than hooking
  // every individual accept/reject call site, since that transition already
  // uniquely identifies "just finished deciding, ready to re-upload"
  // regardless of which decision path (bulk accept/reject/partial) got there.
  // undefined -> true (e.g. on initial load of an already-fully-decided
  // report) deliberately does NOT fire this — only a real transition does.
  const [showIncorporateDialog, setShowIncorporateDialog] = useState(false);
  const prevCanUploadRef = useRef<boolean | undefined>(undefined);
  useEffect(() => {
    const prev = prevCanUploadRef.current;
    if (prev === false && state?.can_upload === true) {
      setShowIncorporateDialog(true);
    }
    prevCanUploadRef.current = state?.can_upload;
  }, [state?.can_upload]);

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
        <p>Complete the earlier steps first — RC, Impact & CAPA Critique needs this investigation's record to exist.</p>
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

  // Shared by every RecommendationGroup instance below — each group drives
  // its own blanket accept/reject UI, but every actual decision still goes
  // through this one page-level call (and updates the one shared `state`).
  function decideRecommendation(recommendationId: number, decision: "accepted" | "rejected", reason?: string) {
    return decideRcCapaRecommendation(recordId!, recommendationId, decision, reason);
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

  const report = state.latest_report;
  const allRecsFlat = report?.critiques.flatMap((c) => c.recommendations) ?? [];
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
        <p className="card-title">RC, Impact & CAPA Critique</p>
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
              All observations have been resolved and the RC, Impact & CAPA Critique is fully completed.
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
            <button type="button" className="btn-outline" onClick={() => setShowScoreDetails(true)}>
              Score Details
            </button>
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
          <p className="card-title">{state.upload_count === 0 ? "Upload Report" : "Upload Updated RC, Impact & CAPA Critique"}</p>
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
                                <RecommendationGroup
                                  recs={rootCauseRecs}
                                  allRecsFlat={allRecsFlat}
                                  decisionBusy={decisionBusy}
                                  decide={decideRecommendation}
                                  onDecided={setState}
                                  setDecisionBusy={setDecisionBusy}
                                  setDecisionError={setDecisionError}
                                  setScoring={setScoring}
                                />
                              </div>
                            )}
                            {impactRecs.length > 0 && (
                              <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-card-border)", borderRadius: 10, padding: "13px 17px", display: "flex", flexDirection: "column", gap: 8 }}>
                                <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-base)" }}>Impact Assessment</p>
                                <RecommendationGroup
                                  recs={impactRecs}
                                  allRecsFlat={allRecsFlat}
                                  decisionBusy={decisionBusy}
                                  decide={decideRecommendation}
                                  onDecided={setState}
                                  setDecisionBusy={setDecisionBusy}
                                  setDecisionError={setDecisionError}
                                  setScoring={setScoring}
                                />
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </>
                  ) : (
                    <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-card-border)", borderRadius: 10, padding: "13px 17px", display: "flex", flexDirection: "column", gap: 8 }}>
                      <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-base)" }}>Recommendations for Improvements</p>
                      <RecommendationGroup
                        recs={critique.recommendations}
                        allRecsFlat={allRecsFlat}
                        decisionBusy={decisionBusy}
                        decide={decideRecommendation}
                        onDecided={setState}
                        setDecisionBusy={setDecisionBusy}
                        setDecisionError={setDecisionError}
                        setScoring={setScoring}
                      />
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
          message="Are you sure you want to accept and push the RC, Impact & CAPA Critique for SIT Review?"
          onCancel={() => setShowConfirm(false)}
          onConfirm={handlePushToSitReview}
        />
      )}

      {scoring && <ScoringDialog reason={scoring} />}

      {showScoreDetails && report && <ScoreDetailsDialog report={report} onClose={() => setShowScoreDetails(false)} />}

      {showHistory && (
        <RcCapaHistoryPanel reports={historyReports} loading={historyLoading} onClose={() => setShowHistory(false)} />
      )}

      {showIncorporateDialog && <IncorporateChangesDialog onClose={() => setShowIncorporateDialog(false)} />}
    </div>
  );
}