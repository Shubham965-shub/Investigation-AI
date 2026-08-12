import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { getProblemStatementRecord } from "../api/dashboard";
import { ApiError } from "../api/client";
import { DbErrorModal } from "../components/DbErrorModal";
import exportIcon from "../assets/icons/rci-export-icon.svg";
import "./RecordModulePage.css";

// Shell only (2026-08-12, per the user) — the real ds agent (agents/rci_report,
// merged into ds this session) has no backend router or persistence on our
// side yet, and no GET endpoint exists to fetch a generated report. Every
// section below renders a placeholder body rather than fabricated content
// until that real data flow is built. Section list/order matches ds's 11
// RciReport* schemas (api/schemas/define.py, measure_analyze.py,
// improve_control.py) exactly.
const SECTIONS: { key: string; label: string }[] = [
  { key: "executive-summary", label: "1 Executive Summary" },
  { key: "description-of-event", label: "2 Description of Event" },
  { key: "initial-impact-assessment", label: "3 Initial Impact Assessment" },
  { key: "history-review", label: "4 Summary of History Review" },
  { key: "investigation-task", label: "5 Investigation Task" },
  { key: "root-cause", label: "6 Root Cause" },
  { key: "impact-assessment-batch-disposition", label: "7 Impact Assessment & Conclusion (Batch Disposition)" },
  { key: "risk-assessment", label: "8 Risk Assessment" },
  { key: "correction-remedial-action", label: "9 Correction & Remedial Action" },
  { key: "capa", label: "10 Corrective Action & Preventive Action (CAPA)" },
  { key: "capa-effectiveness-check-plan", label: "11 CAPA Effectiveness Check Plan" },
];

export function RciReportPage() {
  const { recordId } = useParams<{ recordId: string }>();

  const [loading, setLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [problemStatement, setProblemStatement] = useState<string | null>(null);

  const [openSections, setOpenSections] = useState<Record<string, boolean>>({});
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    setLoading(true);
    setDbError(null);
    (async () => {
      try {
        const data = await getProblemStatementRecord(recordId);
        if (cancelled) return;
        setProblemStatement(data?.problem_statement ?? null);
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

  function jumpToSection(key: string) {
    setOpenSections((prev) => ({ ...prev, [key]: true }));
    sectionRefs.current[key]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card-header">
        <div>
          <p className="card-title" style={{ marginBottom: 4 }}>RCI Investigation Report</p>
          <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
            Comprehensive summary of the investigation process and findings.
          </p>
        </div>
        <button
          type="button"
          className="btn-primary"
          style={{ display: "flex", alignItems: "center", gap: 10, opacity: 0.4, cursor: "default" }}
          disabled
          title="Not available yet — report generation isn't wired up"
        >
          <img src={exportIcon} alt="" width={16} height={16} />
          Accept & Push to TW
        </button>
      </div>

      <div className="card" style={{ gap: 8 }}>
        <p style={{ margin: 0, fontWeight: 700, fontSize: "var(--font-size-lg)" }}>Problem Statement</p>
        <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12 }}>
          <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
            {problemStatement || "No problem statement recorded for this investigation yet."}
          </p>
        </div>
      </div>

      <div
        style={{
          background: "var(--color-primary)",
          color: "#fff",
          borderRadius: 10,
          padding: "20px 24px",
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        <p style={{ margin: 0, fontSize: "var(--font-size-xs)", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", opacity: 0.85 }}>
          Root Cause Investigation Report
        </p>
        <p style={{ margin: 0, fontSize: "var(--font-size-lg)", fontWeight: 700 }}>Record Details — REC-{recordId}</p>
        <span
          style={{
            alignSelf: "flex-start",
            fontSize: "var(--font-size-sm)",
            fontWeight: 600,
            background: "rgba(255,255,255,0.15)",
            border: "1px solid rgba(255,255,255,0.4)",
            borderRadius: 99,
            padding: "4px 12px",
          }}
        >
          Not yet generated
        </span>
      </div>

      <div className="card" style={{ gap: 12 }}>
        <p style={{ margin: 0, fontWeight: 700, color: "var(--color-primary)" }}>View Section:</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              type="button"
              className="btn-outline"
              style={{ fontSize: "var(--font-size-sm)" }}
              onClick={() => jumpToSection(s.key)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {SECTIONS.map((s) => {
          const isOpen = !!openSections[s.key];
          return (
            <div
              key={s.key}
              ref={(el) => {
                sectionRefs.current[s.key] = el;
              }}
              className="card"
              style={{ gap: 0, padding: 0, overflow: "hidden" }}
            >
              <button
                type="button"
                onClick={() => setOpenSections((prev) => ({ ...prev, [s.key]: !prev[s.key] }))}
                style={{
                  background: "none",
                  border: "none",
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "16px 20px",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                <span style={{ flex: 1, fontWeight: 600, fontSize: "var(--font-size-base)" }}>{s.label}</span>
                <span style={{ fontSize: "var(--font-size-md)", color: "var(--color-text-muted)", transform: isOpen ? "rotate(180deg)" : "none" }}>
                  ⌄
                </span>
              </button>
              {isOpen && (
                <div style={{ padding: "0 20px 20px", borderTop: "1px solid var(--color-card-border)" }}>
                  <p style={{ margin: "16px 0 0", fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
                    This section hasn't been generated yet — RCI Report generation isn't wired up on the backend yet.
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}