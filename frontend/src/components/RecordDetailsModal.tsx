import { useState } from "react";
import modalClose from "../assets/icons/modal-close.svg";
import recordDocIcon from "../assets/icons/modal-record-doc.svg";
import chevronRight from "../assets/icons/modal-chevron-right.svg";
import copyIcon from "../assets/icons/copy-icon.svg";
import { ApiError } from "../api/client";
import { getSimilarInvestigations, type SimilarInvestigation } from "../api/dashboard";

const STATUS_BADGE_STYLE: Record<SimilarInvestigation["status"], { bg: string; color: string }> = {
  Open: { bg: "#eff6ff", color: "#1d4ed8" },
  Closed: { bg: "#f0fdf4", color: "#15803d" },
  Cancelled: { bg: "#f3f4f6", color: "#4b5563" },
  Unknown: { bg: "#f3f4f6", color: "#4b5563" },
};

// Matches the approved Figma "Home<Problem_Statement_Generated" modal
// (node 1229:31224) — appears automatically when landing on the Problem
// Statement step for a record that already has a saved problem statement.

export function RecordDetailsModal({
  recordId,
  problemStatement,
  onClose,
  onSaveEdit,
  onSaveAndNext,
  onViewRecordDetails,
}: {
  recordId: string;
  problemStatement: string;
  onClose: () => void;
  onSaveEdit: (newText: string) => void;
  onSaveAndNext: () => void;
  onViewRecordDetails: () => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(problemStatement);
  const [historicExpanded, setHistoricExpanded] = useState(false);
  const [historicData, setHistoricData] = useState<SimilarInvestigation[] | null>(null);
  const [historicLoading, setHistoricLoading] = useState(false);
  const [historicError, setHistoricError] = useState<string | null>(null);

  function handleCopy() {
    navigator.clipboard.writeText(problemStatement);
  }

  function handleToggleHistoric() {
    const next = !historicExpanded;
    setHistoricExpanded(next);
    if (next && historicData === null && !historicLoading) {
      setHistoricLoading(true);
      setHistoricError(null);
      getSimilarInvestigations(recordId)
        .then(setHistoricData)
        .catch((err) => setHistoricError(err instanceof ApiError ? String(err.detail) : "Could not load historic data."))
        .finally(() => setHistoricLoading(false));
    }
  }

  function handleEditClick() {
    setDraft(problemStatement);
    setIsEditing(true);
  }

  function handleSaveClick() {
    onSaveEdit(draft);
    setIsEditing(false);
  }

  function handleCancelClick() {
    setIsEditing(false);
  }

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(73, 84, 80, 0.45)", zIndex: 60 }} />
      <div
        role="dialog"
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          background: "var(--color-surface)",
          borderRadius: 10,
          width: "min(1102px, 92vw)",
          maxHeight: "88vh",
          overflowY: "auto",
          zIndex: 61,
        }}
      >
        <div style={{ borderBottom: "1px solid var(--color-card-border)", padding: "16px 16px 17px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <p style={{ margin: 0, fontWeight: 700, fontSize: 20, color: "var(--color-text)" }}>Record Details - REC - {recordId}</p>
          <button type="button" aria-label="Close" onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}>
            <img src={modalClose} alt="" width={32} height={32} />
          </button>
        </div>

        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 32 }}>
          <button
            type="button"
            onClick={onViewRecordDetails}
            style={{
              background: "var(--color-surface)",
              border: "1px solid var(--color-card-border)",
              borderRadius: 10,
              padding: "8px 12px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              cursor: "pointer",
              textAlign: "left",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ background: "var(--color-rail-active-bg)", borderRadius: "50%", width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <img src={recordDocIcon} alt="" width={16} height={16} />
              </span>
              <div>
                <p style={{ margin: 0, fontWeight: 600, fontSize: 20, color: "var(--color-text)" }}>View Record Details</p>
                <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>See all information for REC - {recordId}</p>
              </div>
            </div>
            <img src={chevronRight} alt="" width={20} height={20} />
          </button>

          <div style={{ border: "1px solid var(--color-card-border)", borderRadius: 8, padding: 16, display: "flex", flexDirection: "column", gap: 28 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <p style={{ margin: 0, fontWeight: 600, fontSize: 20, color: "var(--color-text)" }}>Problem Statement</p>
              <button type="button" onClick={handleCopy} className="btn-outline">
                <img src={copyIcon} alt="" width={18} height={18} />
                Copy
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              {isEditing ? (
                <textarea
                  className="field-value"
                  autoFocus
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={5}
                  style={{ fontWeight: 600, fontSize: 20, lineHeight: 1.6 }}
                />
              ) : (
                <p style={{ margin: 0, fontWeight: 600, fontSize: 24, lineHeight: 1.8, color: "var(--color-text)" }}>{problemStatement}</p>
              )}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
                {isEditing ? (
                  <>
                    <button type="button" onClick={handleCancelClick} className="btn-outline">
                      Cancel
                    </button>
                    <button type="button" onClick={handleSaveClick} className="btn-primary">
                      Save
                    </button>
                  </>
                ) : (
                  <button type="button" onClick={handleEditClick} className="btn-secondary" style={{ background: "none" }}>
                    Edit Problem Statement
                  </button>
                )}
              </div>
            </div>
          </div>

          <div>
            <button type="button" onClick={handleToggleHistoric} className="btn-outline">
              View Historic Data
              <img
                src={chevronRight}
                alt=""
                width={20}
                height={20}
                style={{ transform: historicExpanded ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 150ms ease" }}
              />
            </button>

            {historicExpanded && (
              <div
                style={{
                  border: "1px solid var(--color-card-border)",
                  borderRadius: 8,
                  marginTop: 8,
                  padding: 12,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                {historicLoading && <p style={{ margin: 0, color: "var(--color-text-muted)" }}>Loading similar investigations…</p>}
                {historicError && <p style={{ margin: 0, color: "#b91c1c" }}>{historicError}</p>}
                {!historicLoading && !historicError && historicData !== null && historicData.length === 0 && (
                  <p style={{ margin: 0, color: "var(--color-text-muted)" }}>No similar historic investigations found.</p>
                )}
                {!historicLoading &&
                  !historicError &&
                  historicData?.map((item) => {
                    const badge = STATUS_BADGE_STYLE[item.status];
                    return (
                      <div
                        key={item.deviation_id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: 12,
                          padding: "8px 12px",
                          background: "var(--color-bg)",
                          borderRadius: 6,
                        }}
                      >
                        <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                          <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>REC - {item.deviation_id}</span>
                          <span style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text)" }}>{item.title}</span>
                        </div>
                        <span
                          style={{
                            flexShrink: 0,
                            fontSize: 12,
                            fontWeight: 600,
                            padding: "3px 10px",
                            borderRadius: 999,
                            background: badge.bg,
                            color: badge.color,
                          }}
                        >
                          {item.status}
                        </span>
                      </div>
                    );
                  })}
              </div>
            )}
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button type="button" onClick={onSaveAndNext} className="btn-primary">
              Save &amp; Next
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
