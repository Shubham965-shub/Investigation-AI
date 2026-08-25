import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  getProblemStatementRecord,
  getRciReportRecord,
  generateRciReport,
  updateRciReportSections,
  exportRciReportDocx,
  RCA_METHOD_OPTIONS,
  SIX_M_FACTOR_OPTIONS,
  DURATION_TIER_OPTIONS,
  CAPA_MECHANISM_OPTIONS,
  IMPACT_SUBSECTION_FIELDS,
  type RciReportSections,
  type SourcedTextItem,
  type MaterialProductImpactItem,
  type EquipmentImpactItem,
  type HistoryReviewRow,
  type InvestigationTaskGroup,
  type InvestigationTaskSubsection,
  type InvestigationTaskFinding,
  type ImpactSubsectionItem,
  type BatchShipperImpact,
  type RiskAssessmentCandidate,
  type SeverityTier,
  type RepeatabilityTier,
  type DetectabilityTier,
  type ObservationStatusItem,
  type CAPAActionItem,
  type InterimControlItem,
  type CAPAEffectivenessPlanItem,
  type RCAMethod,
  type SixMFactor,
} from "../api/dashboard";
import { ApiError } from "../api/client";
import { DbErrorModal } from "../components/DbErrorModal";
import exportIcon from "../assets/icons/rci-export-icon.svg";
import chevronIcon from "../assets/icons/rci-report-chevron.svg";
import iconExecutiveSummary from "../assets/icons/rci-report-icon-executive-summary.svg";
import iconDescription from "../assets/icons/rci-report-icon-description.svg";
import iconImpactAssessment from "../assets/icons/rci-report-icon-impact-assessment.svg";
import iconHistoryReview from "../assets/icons/rci-report-icon-history-review.svg";
import iconRootCause from "../assets/icons/rci-report-icon-root-cause.svg";
import iconBatchDisposition from "../assets/icons/rci-report-icon-batch-disposition.svg";
import iconRiskAssessment from "../assets/icons/rci-report-icon-risk-assessment.svg";
import iconRemedialAction from "../assets/icons/rci-report-icon-remedial-action.svg";
import iconCapa from "../assets/icons/rci-report-icon-capa.svg";
import iconEffectivenessCheck from "../assets/icons/rci-report-icon-effectiveness-check.svg";
import penIcon from "../assets/icons/rci-pen-icon.svg";
import checkSingleIcon from "../assets/icons/rci-report-check-single.svg";
import checkDoubleIcon from "../assets/icons/rci-report-check-double.svg";
import "./RecordModulePage.css";

const EditModeContext = createContext(false);

type SectionMeta = { key: string; number: number; title: string; icon: string; subtitle?: string };

const SECTIONS: SectionMeta[] = [
  { key: "executive-summary", number: 1, title: "Executive Summary", icon: iconExecutiveSummary },
  { key: "description-of-event", number: 2, title: "Description of Event", icon: iconDescription },
  { key: "initial-impact-assessment", number: 3, title: "Initial Impact Assessment & Immediate Actions", icon: iconImpactAssessment },
  {
    key: "history-review",
    number: 4,
    title: "Summary of History Review",
    icon: iconHistoryReview,
    subtitle: "24-month lookback across product, equipment, and area",
  },
  { key: "investigation-task", number: 5, title: "Investigation Task", icon: iconDescription, subtitle: "Root Cause Conclusion" },
  { key: "root-cause", number: 6, title: "Root Cause", icon: iconRootCause },
  {
    key: "impact-assessment-batch-disposition",
    number: 7,
    title: "Impact Assessment & Conclusion (Batch Disposition)",
    icon: iconBatchDisposition,
  },
  {
    key: "risk-assessment",
    number: 8,
    title: "Risk Assessment",
    icon: iconRiskAssessment,
    subtitle: "RPN calculation for root cause and probable root cause",
  },
  { key: "correction-remedial-action", number: 9, title: "Correction & Remedial Action", icon: iconRemedialAction },
  { key: "capa", number: 10, title: "Corrective Action & Preventive Action (CAPA)", icon: iconCapa },
  { key: "capa-effectiveness-check-plan", number: 11, title: "CAPA Effectiveness Check Plan", icon: iconEffectivenessCheck },
];

const SOURCE_OPTIONS: SourcedTextItem["source"][] = ["trackwise", "manual_entry_required", "manual_entry_provided", "synthesized"];

// Matches the app's existing table-header convention (see .ac-table thead th
// in ActionCenterPage.css) — reused here for every read-mode section label
// so this page's typography doesn't drift from the rest of the app.
const READ_LABEL_STYLE: React.CSSProperties = {
  margin: 0,
  fontWeight: 700,
  fontSize: "var(--font-size-xs)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "var(--color-text-muted)",
};

// Shown in place of a section's fields when ds skipped it — either a
// required TrackWise field was blank, or a section it depends on was itself
// skipped (2026-08-24, per the user: this must not break the sections that
// DID generate, and should point the investigator at what to go fill in).
function MissingFieldsNotice({ message }: { message?: string }) {
  return (
    <div style={{ background: "var(--color-warning-bg)", border: "1px solid var(--color-warning-text)", borderRadius: "var(--radius-card)", padding: 16, display: "flex", flexDirection: "column", gap: 4 }}>
      <p style={{ margin: 0, fontWeight: 700, color: "var(--color-warning-text)", fontSize: "var(--font-size-base)" }}>
        This section could not be generated
      </p>
      <p style={{ margin: 0, fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
        The related TrackWise field(s) aren't filled — please fill them and regenerate.
      </p>
      {message && <p style={{ margin: 0, fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>{message}</p>}
    </div>
  );
}

// ── Small shared field primitives ─────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  const editing = useContext(EditModeContext);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <p
        className={editing ? "field-label" : undefined}
        style={editing ? { margin: 0 } : READ_LABEL_STYLE}
      >
        {label}
      </p>
      {children}
    </div>
  );
}

function DataTable<T>({ columns, rows }: { columns: { key: string; label: string }[]; rows: (T & { _cell?: (key: string) => React.ReactNode })[] }) {
  return (
    <div style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, overflow: "hidden" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--font-size-sm)" }}>
        <thead>
          <tr style={{ background: "var(--color-bg)" }}>
            {columns.map((c) => (
              <th key={c.key} style={{ ...READ_LABEL_STYLE, textAlign: "left", padding: "10px 12px", borderBottom: "1px solid var(--color-card-border)" }}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderTop: i > 0 ? "1px solid var(--color-card-border)" : undefined }}>
              {columns.map((c) => (
                <td key={c.key} style={{ padding: "10px 12px", verticalAlign: "top" }}>
                  {row._cell ? row._cell(c.key) : (row as Record<string, React.ReactNode>)[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChecklistRow({ text }: { text: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 6, padding: "8px 12px" }}>
      <span style={{ color: "var(--color-success-text)", flex: "0 0 auto" }}>&#10003;</span>
      <span style={{ fontSize: "var(--font-size-base)" }}>{text}</span>
    </div>
  );
}

function SectionFooter({
  editing,
  onToggleEdit,
  read,
  onToggleRead,
}: {
  editing: boolean;
  onToggleEdit: () => void;
  read: boolean;
  onToggleRead: () => void;
}) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 16, marginTop: 4 }}>
      <button
        type="button"
        onClick={onToggleRead}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: 0,
          color: "var(--color-success-text)",
          fontWeight: 600,
          fontSize: "var(--font-size-sm)",
        }}
      >
        <img src={read ? checkDoubleIcon : checkSingleIcon} alt="" width={read ? 18 : 14} height={14} />
        {read ? "Read" : "Mark as Read"}
      </button>
      <button
        type="button"
        className="btn-outline"
        disabled={read}
        title={read ? "Unmark as read to edit this section" : undefined}
        style={{ display: "flex", alignItems: "center", gap: 8, background: editing ? "var(--color-rail-active-bg)" : undefined, opacity: read ? 0.5 : 1, cursor: read ? "not-allowed" : "pointer" }}
        onClick={onToggleEdit}
      >
        <img src={penIcon} alt="" width={14} height={14} />
        {editing ? "Done Editing" : "Edit"}
      </button>
    </div>
  );
}

function ReadOnlyValue({ value }: { value: string }) {
  return <p className="field-value" style={{ margin: 0, whiteSpace: "pre-wrap", background: "none", border: "none", padding: "6px 0" }}>{value || "—"}</p>;
}

function TextInput({
  value,
  onChange,
  placeholder,
  style,
  type = "text",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  style?: React.CSSProperties;
  type?: string;
}) {
  const editing = useContext(EditModeContext);
  if (!editing) return <ReadOnlyValue value={value} />;
  return <input type={type} className="field-value" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} style={style} />;
}

function TextArea({
  value,
  onChange,
  rows = 3,
  placeholder,
  style,
}: {
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  placeholder?: string;
  style?: React.CSSProperties;
}) {
  const editing = useContext(EditModeContext);
  if (!editing) return <ReadOnlyValue value={value} />;
  return (
    <textarea
      className="field-value"
      rows={rows}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      style={{ resize: "vertical", ...style }}
    />
  );
}

function EditOnly({ children }: { children: React.ReactNode }) {
  return useContext(EditModeContext) ? <>{children}</> : null;
}

function SelectInput<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: readonly T[] }) {
  const editing = useContext(EditModeContext);
  if (!editing) return <ReadOnlyValue value={value} />;
  return (
    <select className="field-value" value={value} onChange={(e) => onChange(e.target.value as T)}>
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}

function CheckboxField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  const editing = useContext(EditModeContext);
  if (!editing) {
    return (
      <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "var(--font-size-base)" }}>
        <span style={{ color: checked ? "var(--color-primary)" : "var(--color-text-muted)" }}>{checked ? "✓" : "✕"}</span>
        {label}
      </span>
    );
  }
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "var(--font-size-base)", cursor: "pointer" }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function SourcedTextEditor({ label, value, onChange }: { label: string; value: SourcedTextItem; onChange: (v: SourcedTextItem) => void }) {
  const editing = useContext(EditModeContext);
  if (!editing) {
    return (
      <Field label={label}>
        <p style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: "var(--font-size-base)" }}>{value.value || "—"}</p>
      </Field>
    );
  }
  return (
    <div style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
      <Field label={label}>
        <TextArea value={value.value} rows={2} onChange={(v) => onChange({ ...value, value: v })} />
      </Field>
      <Field label="Source">
        <SelectInput value={value.source} onChange={(v) => onChange({ ...value, source: v })} options={SOURCE_OPTIONS} />
      </Field>
    </div>
  );
}

function StringListEditor({ items, onChange, placeholder }: { items: string[]; onChange: (items: string[]) => void; placeholder?: string }) {
  const editing = useContext(EditModeContext);
  const [draft, setDraft] = useState("");
  if (!editing) {
    if (!items.length) return <ReadOnlyValue value="" />;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {items.map((item, i) => (
          <ChecklistRow key={i} text={item} />
        ))}
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {items.map((item, i) => (
        <div key={i} style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input className="field-value" value={item} onChange={(e) => onChange(items.map((it, j) => (j === i ? e.target.value : it)))} style={{ flex: 1 }} />
          <button type="button" className="btn-outline" onClick={() => onChange(items.filter((_, j) => j !== i))}>
            Remove
          </button>
        </div>
      ))}
      <div style={{ display: "flex", gap: 8 }}>
        <input
          className="field-value"
          value={draft}
          placeholder={placeholder ?? "Add an item…"}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && draft.trim()) {
              e.preventDefault();
              onChange([...items, draft.trim()]);
              setDraft("");
            }
          }}
          style={{ flex: 1 }}
        />
        <button
          type="button"
          className="btn-outline"
          disabled={!draft.trim()}
          onClick={() => {
            if (!draft.trim()) return;
            onChange([...items, draft.trim()]);
            setDraft("");
          }}
        >
          Add
        </button>
      </div>
    </div>
  );
}

function ChipMultiSelect<T extends string>({ options, selected, onChange }: { options: readonly T[]; selected: T[]; onChange: (v: T[]) => void }) {
  const editing = useContext(EditModeContext);
  if (!editing) {
    if (!selected.length) return <ReadOnlyValue value="" />;
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {selected.map((o) => (
          <span
            key={o}
            style={{ fontSize: "var(--font-size-sm)", background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 6, padding: "4px 10px" }}
          >
            {o}
          </span>
        ))}
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {options.map((o) => {
        const isSelected = selected.includes(o);
        return (
          <button
            key={o}
            type="button"
            className="btn-outline"
            style={{
              fontSize: "var(--font-size-sm)",
              background: isSelected ? "var(--color-primary)" : undefined,
              color: isSelected ? "#fff" : undefined,
            }}
            onClick={() => onChange(isSelected ? selected.filter((s) => s !== o) : [...selected, o])}
          >
            {o}
          </button>
        );
      })}
    </div>
  );
}

function ImpactSubsectionEditor({
  label,
  value,
  onChange,
  extra,
}: {
  label: string;
  value: ImpactSubsectionItem;
  onChange: (v: ImpactSubsectionItem) => void;
  extra?: React.ReactNode;
}) {
  const editing = useContext(EditModeContext);
  if (!editing) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <p style={READ_LABEL_STYLE}>{label}</p>
        <p style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: "var(--font-size-base)" }}>{value.narrative || "—"}</p>
        {extra}
      </div>
    );
  }
  return (
    <div style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <p style={{ margin: 0, fontWeight: 600 }}>{label}</p>
        <CheckboxField label="Applicable" checked={value.applicable} onChange={(v) => onChange({ ...value, applicable: v })} />
      </div>
      <TextArea value={value.narrative} rows={2} onChange={(v) => onChange({ ...value, narrative: v })} />
      {extra}
    </div>
  );
}

function SectionCard({
  section,
  isOpen,
  onToggle,
  editing,
  onToggleEdit,
  read,
  onToggleRead,
  setRef,
  children,
}: {
  section: SectionMeta;
  isOpen: boolean;
  onToggle: () => void;
  editing: boolean;
  onToggleEdit: () => void;
  read: boolean;
  onToggleRead: () => void;
  setRef: (el: HTMLDivElement | null) => void;
  children: React.ReactNode;
}) {
  return (
    <div ref={setRef} className="card" style={{ gap: 0, padding: 0, overflow: "hidden" }} key={section.key}>
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") onToggle();
        }}
        style={{ background: "none", border: "none", width: "100%", display: "flex", alignItems: "center", gap: 16, padding: "16px 20px", cursor: "pointer", textAlign: "left" }}
      >
        <span
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 36,
            height: 36,
            flex: "0 0 auto",
            borderRadius: 10,
            background: "var(--color-rail-active-bg)",
          }}
        >
          <img src={section.icon} alt="" width={16} height={16} />
        </span>
        <span style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span
              style={{
                fontSize: "var(--font-size-xs)",
                fontWeight: 700,
                color: "var(--color-primary)",
                background: "var(--color-rail-active-bg)",
                borderRadius: 4,
                padding: "1px 6px",
              }}
            >
              {section.number}
            </span>
            <span style={{ fontWeight: 600, fontSize: "var(--font-size-base)", color: "var(--color-text)" }}>{section.title}</span>
          </span>
          {section.subtitle && (
            <span style={{ fontSize: "var(--font-size-xs)", fontWeight: 500, color: "var(--color-text-muted)" }}>{section.subtitle}</span>
          )}
        </span>
        <img
          src={chevronIcon}
          alt=""
          width={32}
          height={32}
          style={{ flex: "0 0 auto", transform: isOpen ? "none" : "rotate(180deg)" }}
        />
      </div>
      {isOpen && (
        <div style={{ padding: "0 20px 20px", borderTop: "1px solid var(--color-card-border)", display: "flex", flexDirection: "column", gap: 16, marginTop: 16 }}>
          <EditModeContext.Provider value={editing && !read}>{children}</EditModeContext.Provider>
          <SectionFooter editing={editing && !read} onToggleEdit={onToggleEdit} read={read} onToggleRead={onToggleRead} />
        </div>
      )}
    </div>
  );
}

// ── Page ────────────────────────────────────────────────────────────────

export function RciReportPage() {
  const { recordId } = useParams<{ recordId: string }>();

  const [loading, setLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [problemStatement, setProblemStatement] = useState<string | null>(null);
  const [rciNumber, setRciNumber] = useState<string | null>(null);

  const [report, setReport] = useState<RciReportSections | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);

  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [editSections, setEditSections] = useState<Record<string, boolean>>({});
  const [readSections, setReadSections] = useState<Record<string, boolean>>({});

  const [openSections, setOpenSections] = useState<Record<string, boolean>>({});
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const persistTimerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    setLoading(true);
    setDbError(null);
    (async () => {
      try {
        const [psRecord, reportRecord] = await Promise.all([getProblemStatementRecord(recordId), getRciReportRecord(recordId)]);
        if (cancelled) return;
        setProblemStatement(psRecord?.problem_statement ?? null);
        if (reportRecord) {
          setReport(reportRecord.report);
          setGeneratedAt(reportRecord.generated_at);
          const rci = reportRecord.trackwise_fields?.["RCI Number"];
          setRciNumber((Array.isArray(rci) ? rci.join(", ") : rci) || null);
        }
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

  function persistReport(newReport: RciReportSections) {
    if (!recordId) return;
    if (persistTimerRef.current) window.clearTimeout(persistTimerRef.current);
    persistTimerRef.current = window.setTimeout(() => {
      updateRciReportSections(recordId, newReport).catch((err) => console.error("Failed to persist RCI report", err));
    }, 600);
  }

  function updateReport(updater: (r: RciReportSections) => RciReportSections) {
    setReport((prev) => {
      if (!prev) return prev;
      const next = updater(prev);
      persistReport(next);
      return next;
    });
  }

  // Generic setter for a single flat field on a top-level section.
  function setSectionField(section: keyof RciReportSections, field: string, value: unknown) {
    updateReport((r) => ({ ...r, [section]: { ...(r[section] as unknown as Record<string, unknown>), [field]: value } } as unknown as RciReportSections));
  }

  // Generic setter for a nested object one level under a section (e.g.
  // description_of_event.nonconforming_reference, root_cause_conclusion.taxonomy,
  // or any of the 10 flat ImpactSubsection fields on impact_assessment_batch_disposition).
  // `patch` deliberately typed `object` (not Record<string, unknown>) so any of
  // this file's concrete typed shapes (SourcedTextItem, ImpactSubsectionItem, ...)
  // can be passed directly without a per-call-site cast.
  function setNestedField(section: keyof RciReportSections, subfield: string, patch: object) {
    updateReport((r) => {
      const sec = r[section] as unknown as Record<string, any>;
      return { ...r, [section]: { ...sec, [subfield]: { ...sec[subfield], ...patch } } } as unknown as RciReportSections;
    });
  }

  // Generic setter for a whole list field on a top-level section.
  function setListField(section: keyof RciReportSections, field: string, newList: unknown[]) {
    updateReport((r) => ({ ...r, [section]: { ...(r[section] as unknown as Record<string, unknown>), [field]: newList } } as unknown as RciReportSections));
  }

  function listHelpers<T>(section: keyof RciReportSections, field: string, currentList: T[]) {
    return {
      add: (item: T) => setListField(section, field, [...currentList, item]),
      remove: (index: number) => setListField(section, field, currentList.filter((_, i) => i !== index)),
      update: (index: number, patch: Partial<T>) =>
        setListField(section, field, currentList.map((it, i) => (i === index ? { ...it, ...patch } : it))),
    };
  }

  function toggleSection(key: string) {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function toggleEditSection(key: string) {
    setEditSections((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function toggleReadSection(key: string) {
    setReadSections((prev) => {
      const next = !prev[key];
      if (next) setEditSections((es) => ({ ...es, [key]: false }));
      return { ...prev, [key]: next };
    });
  }

  function jumpToSection(key: string) {
    setOpenSections((prev) => ({ ...prev, [key]: true }));
    sectionRefs.current[key]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function handleGenerate() {
    if (!recordId) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const record = await generateRciReport(recordId);
      setReport(record.report);
      setGeneratedAt(record.generated_at);
    } catch (err) {
      setGenerateError(err instanceof ApiError ? String(err.detail) : "Failed to generate RCI Report");
    } finally {
      setGenerating(false);
    }
  }

  // Real .docx download for "Download and View" (2026-08-25, per the user)
  // — the backend fills the company's actual RCI Report Word template with
  // this investigation's persisted report and returns the file directly,
  // same convention as RCI Plan's own export. Also opens it in a new tab
  // (best-effort "view" — most browsers still just re-download a .docx,
  // since none render it natively, but this hands it off to whatever the
  // OS/browser has registered for the file type instead of only saving it).
  async function handleDownloadAndView() {
    if (!recordId) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      const blob = await exportRciReportDocx(recordId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `RCI_Report_${recordId}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.open(url, "_blank");
      // Revoking immediately can race the new tab's own load of the same
      // blob URL — give it a moment first.
      window.setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (err) {
      setDownloadError(err instanceof ApiError ? String(err.detail) : "Failed to export the RCI report document");
    } finally {
      setDownloading(false);
    }
  }

  // Gates "Download and View" on every section having been marked read
  // (2026-08-24, per the user).
  const allSectionsRead = !!report && SECTIONS.every((s) => readSections[s.key]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card-header" style={{ justifyContent: "flex-end" }}>
        <button
          type="button"
          className="btn-primary"
          style={{ display: "flex", alignItems: "center", gap: 10, opacity: allSectionsRead ? 1 : 0.4, cursor: allSectionsRead && !downloading ? "pointer" : "default" }}
          disabled={!allSectionsRead || downloading}
          title={allSectionsRead ? undefined : "Mark every section as read to enable this"}
          onClick={handleDownloadAndView}
        >
          <img src={exportIcon} alt="" width={16} height={16} />
          {downloading ? "Downloading…" : "Download and View"}
        </button>
      </div>
      {downloadError && <p className="error-banner">{downloadError}</p>}

      <div className="card" style={{ gap: 8 }}>
        <p style={{ margin: 0, fontWeight: 700, fontSize: "var(--font-size-lg)" }}>Problem Statement</p>
        <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12 }}>
          <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
            {problemStatement || "No problem statement recorded for this investigation yet."}
          </p>
        </div>
      </div>

      <div style={{ background: "var(--color-primary)", color: "#fff", borderRadius: 10, padding: "20px 24px", display: "flex", flexDirection: "column", gap: 10 }}>
        <p style={{ margin: 0, fontSize: "var(--font-size-xs)", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", opacity: 0.85 }}>
          Root Cause Investigation Report
        </p>
        <p style={{ margin: 0, fontSize: "var(--font-size-lg)", fontWeight: 700 }}>Record Details — RCI Record-{rciNumber ?? recordId}</p>
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
          {report ? `Generated ${generatedAt ? new Date(generatedAt).toLocaleString() : ""}` : "Not yet generated"}
        </span>
      </div>

      {!report && (
        <div className="card" style={{ gap: 12 }}>
          <p className="card-title">Generate RCI Report</p>
          {generateError && <p className="error-banner">{generateError}</p>}
          <div className="footer-actions">
            <button type="button" className="btn-primary" onClick={handleGenerate} disabled={generating}>
              {generating ? "Generating…" : "Generate RCI Report"}
            </button>
          </div>
        </div>
      )}

      {report && (
        <>
          <div className="card" style={{ gap: 12 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <p style={{ margin: 0, fontWeight: 700, color: "var(--color-primary)" }}>View Section:</p>
              <button type="button" className="btn-outline" onClick={handleGenerate} disabled={generating}>
                {generating ? "Regenerating…" : "Regenerate"}
              </button>
            </div>
            {generateError && <p className="error-banner">{generateError}</p>}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {SECTIONS.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => jumpToSection(s.key)}
                  style={{
                    fontSize: "var(--font-size-sm)",
                    fontWeight: 600,
                    color: "var(--color-primary)",
                    background: "var(--color-surface)",
                    border: "1px solid var(--color-primary)",
                    borderRadius: "var(--radius-btn)",
                    padding: "4px 10px",
                    cursor: "pointer",
                  }}
                >
                  {s.number} {s.title}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {/* 1. Executive Summary */}
            <SectionCard
              section={SECTIONS[0]}
              isOpen={!!openSections["executive-summary"]}
              onToggle={() => toggleSection("executive-summary")}
              editing={!!editSections["executive-summary"]}
              onToggleEdit={() => toggleEditSection("executive-summary")}
              read={!!readSections["executive-summary"]}
              onToggleRead={() => toggleReadSection("executive-summary")}
              setRef={(el) => (sectionRefs.current["executive-summary"] = el)}
            >
              {!report.executive_summary ? (
                <MissingFieldsNotice message={report.errors.executive_summary} />
              ) : (
                <>
                  {editSections["executive-summary"] ? (
                    <Field label="Summary">
                      <TextArea value={report.executive_summary.summary} onChange={(v) => setSectionField("executive_summary", "summary", v)} />
                    </Field>
                  ) : (
                    <div style={{ background: "var(--color-rail-active-bg)", border: "1px solid var(--color-success-border)", borderRadius: "var(--radius-card)", padding: 16, display: "flex", flexDirection: "column", gap: 6 }}>
                      <p style={{ margin: 0, fontWeight: 700, color: "var(--color-primary)", fontSize: "var(--font-size-base)" }}>Summary</p>
                      <p style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: "var(--font-size-base)" }}>{report.executive_summary.summary}</p>
                    </div>
                  )}
                  {([
                    ["problem_description", "Problem Description"],
                    ["immediate_containment_action", "Immediate Containment Action"],
                    ["determination_of_root_cause", "Determination of Root Cause"],
                    ["root_cause_probable_cause_statement", "Root Cause / Probable Cause Statement"],
                    ["impact_assessment", "Impact Assessment"],
                    ["correction_conclusion_preventive_actions", "Correction, Conclusion & Preventive Actions"],
                    ["conclusion_statement", "Conclusion Statement"],
                  ] as const).map(([field, label]) => (
                    <Field key={field} label={label}>
                      <TextArea value={report.executive_summary![field]} onChange={(v) => setSectionField("executive_summary", field, v)} />
                    </Field>
                  ))}
                </>
              )}
            </SectionCard>

            {/* 2. Description of Event */}
            <SectionCard
              section={SECTIONS[1]}
              isOpen={!!openSections["description-of-event"]}
              onToggle={() => toggleSection("description-of-event")}
              editing={!!editSections["description-of-event"]}
              onToggleEdit={() => toggleEditSection("description-of-event")}
              read={!!readSections["description-of-event"]}
              onToggleRead={() => toggleReadSection("description-of-event")}
              setRef={(el) => (sectionRefs.current["description-of-event"] = el)}
            >
              {!report.description_of_event ? (
                <MissingFieldsNotice message={report.errors.description_of_event} />
              ) : (
                <>
                  <Field label="What Happened">
                    <TextArea value={report.description_of_event.what_happened} onChange={(v) => setSectionField("description_of_event", "what_happened", v)} />
                  </Field>
                  <Field label="When It Happened">
                    <TextInput value={report.description_of_event.when_happened} onChange={(v) => setSectionField("description_of_event", "when_happened", v)} />
                  </Field>
                  <Field label="Who Identified">
                    <TextInput value={report.description_of_event.who_identified} onChange={(v) => setSectionField("description_of_event", "who_identified", v)} />
                  </Field>
                  <Field label="Where It Happened">
                    <TextInput value={report.description_of_event.where_it_happened} onChange={(v) => setSectionField("description_of_event", "where_it_happened", v)} />
                  </Field>
                  <SourcedTextEditor
                    label="Non-Conforming Reference"
                    value={report.description_of_event.nonconforming_reference}
                    onChange={(v) => setNestedField("description_of_event", "nonconforming_reference", v)}
                  />
                  <SourcedTextEditor
                    label="How Detected"
                    value={report.description_of_event.how_detected}
                    onChange={(v) => setNestedField("description_of_event", "how_detected", v)}
                  />
                </>
              )}
            </SectionCard>

            {/* 3. Initial Impact Assessment */}
            <SectionCard
              section={SECTIONS[2]}
              isOpen={!!openSections["initial-impact-assessment"]}
              onToggle={() => toggleSection("initial-impact-assessment")}
              editing={!!editSections["initial-impact-assessment"]}
              onToggleEdit={() => toggleEditSection("initial-impact-assessment")}
              read={!!readSections["initial-impact-assessment"]}
              onToggleRead={() => toggleReadSection("initial-impact-assessment")}
              setRef={(el) => (sectionRefs.current["initial-impact-assessment"] = el)}
            >
              {!report.initial_impact_assessment ? (
                <MissingFieldsNotice message={report.errors.initial_impact_assessment} />
              ) : (
                <>
              <Field label="Material / Product Impacts">
                {(() => {
                  const list = report.initial_impact_assessment!.material_product_impacts;
                  const h = listHelpers<MaterialProductImpactItem>("initial_impact_assessment", "material_product_impacts", list);
                  const editing = editSections["initial-impact-assessment"];
                  if (!editing) {
                    if (!list.length) return <ReadOnlyValue value="" />;
                    const pillColor = (t: string) =>
                      t === "Direct"
                        ? { color: "var(--color-danger-text)", background: "var(--color-danger-bg)" }
                        : t === "Indirect"
                          ? { color: "var(--color-warning-text)", background: "var(--color-warning-bg)" }
                          : { color: "var(--color-text-muted)", background: "var(--color-bg)" };
                    return (
                      <DataTable
                        columns={[
                          { key: "material_product_batch", label: "Material / Product" },
                          { key: "stage", label: "Stage" },
                          { key: "quantity_involved", label: "Quantity Involved" },
                          { key: "quantity_on_hold", label: "Quantity on Hold" },
                          { key: "type_of_impact", label: "Type of Impact" },
                        ]}
                        rows={list.map((item) => ({
                          ...item,
                          _cell: (key: string) =>
                            key === "quantity_on_hold" ? (
                              item.quantity_on_hold.value
                            ) : key === "type_of_impact" ? (
                              <span style={{ ...pillColor(item.type_of_impact), borderRadius: 4, padding: "2px 8px", fontSize: "var(--font-size-sm)", fontWeight: 600 }}>{item.type_of_impact}</span>
                            ) : undefined,
                        }))}
                      />
                    );
                  }
                  return (
                    <>
                      {list.map((item, i) => (
                        <div key={i} style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                          <Field label="Material / Product / Batch">
                            <TextInput value={item.material_product_batch} onChange={(v) => h.update(i, { material_product_batch: v })} />
                          </Field>
                          <Field label="Stage">
                            <TextInput value={item.stage} onChange={(v) => h.update(i, { stage: v })} />
                          </Field>
                          <Field label="Quantity Involved">
                            <TextInput value={item.quantity_involved} onChange={(v) => h.update(i, { quantity_involved: v })} />
                          </Field>
                          <SourcedTextEditor label="Quantity on Hold" value={item.quantity_on_hold} onChange={(v) => h.update(i, { quantity_on_hold: v })} />
                          <Field label="Type of Impact">
                            <SelectInput value={item.type_of_impact} onChange={(v) => h.update(i, { type_of_impact: v })} options={["Direct", "Indirect", "Not applicable"] as const} />
                          </Field>
                          <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => h.remove(i)}>
                            Remove
                          </button>
                        </div>
                      ))}
                      <button
                        type="button"
                        className="btn-outline"
                        style={{ alignSelf: "flex-start" }}
                        onClick={() =>
                          h.add({
                            material_product_batch: "",
                            stage: "",
                            quantity_involved: "",
                            quantity_on_hold: { value: "", source: "manual_entry_provided" },
                            type_of_impact: "Not applicable",
                          })
                        }
                      >
                        + Add Material/Product Impact
                      </button>
                    </>
                  );
                })()}
              </Field>

              <Field label="Equipment Impacts">
                {(() => {
                  const list = report.initial_impact_assessment!.equipment_impacts;
                  const h = listHelpers<EquipmentImpactItem>("initial_impact_assessment", "equipment_impacts", list);
                  const editing = editSections["initial-impact-assessment"];
                  const actionsText = (item: EquipmentImpactItem) => {
                    const lines: string[] = [];
                    if (item.actions_initiated.operation_suspended) lines.push("Operation suspended.");
                    if (item.actions_initiated.on_hold_label_affixed) lines.push("'On Hold' label affixed.");
                    if (item.actions_initiated.other_action_taken) lines.push(`Other action taken${item.actions_initiated.other_action_specify ? ` [Specify: ${item.actions_initiated.other_action_specify}]` : ""}.`);
                    return lines;
                  };
                  if (!editing) {
                    if (!list.length) return <ReadOnlyValue value="" />;
                    return (
                      <DataTable
                        columns={[
                          { key: "equipment_instrument", label: "Equipment / Instrument" },
                          { key: "identification_number", label: "Identification Number / Name" },
                          { key: "actions_initiated", label: "Actions Initiated" },
                        ]}
                        rows={list.map((item) => ({
                          ...item,
                          _cell: (key: string) =>
                            key === "equipment_instrument" ? (
                              item.equipment_instrument.value
                            ) : key === "identification_number" ? (
                              item.identification_number.value
                            ) : key === "actions_initiated" ? (
                              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                {actionsText(item).map((line, li) => (
                                  <span key={li}>{line}</span>
                                ))}
                              </div>
                            ) : undefined,
                        }))}
                      />
                    );
                  }
                  return (
                    <>
                      {list.map((item, i) => (
                        <div key={i} style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                          <SourcedTextEditor label="Equipment / Instrument" value={item.equipment_instrument} onChange={(v) => h.update(i, { equipment_instrument: v })} />
                          <SourcedTextEditor label="Identification Number" value={item.identification_number} onChange={(v) => h.update(i, { identification_number: v })} />
                          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            <CheckboxField
                              label="Operation Suspended"
                              checked={item.actions_initiated.operation_suspended}
                              onChange={(v) => h.update(i, { actions_initiated: { ...item.actions_initiated, operation_suspended: v } })}
                            />
                            <CheckboxField
                              label="On-Hold Label Affixed"
                              checked={item.actions_initiated.on_hold_label_affixed}
                              onChange={(v) => h.update(i, { actions_initiated: { ...item.actions_initiated, on_hold_label_affixed: v } })}
                            />
                            <CheckboxField
                              label="Other Action Taken"
                              checked={item.actions_initiated.other_action_taken}
                              onChange={(v) => h.update(i, { actions_initiated: { ...item.actions_initiated, other_action_taken: v } })}
                            />
                            {item.actions_initiated.other_action_taken && (
                              <Field label="Specify Other Action">
                                <TextInput
                                  value={item.actions_initiated.other_action_specify}
                                  onChange={(v) => h.update(i, { actions_initiated: { ...item.actions_initiated, other_action_specify: v } })}
                                />
                              </Field>
                            )}
                          </div>
                          <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => h.remove(i)}>
                            Remove
                          </button>
                        </div>
                      ))}
                      <button
                        type="button"
                        className="btn-outline"
                        style={{ alignSelf: "flex-start" }}
                        onClick={() =>
                          h.add({
                            equipment_instrument: { value: "", source: "manual_entry_provided" },
                            identification_number: { value: "", source: "manual_entry_provided" },
                            actions_initiated: { operation_suspended: false, on_hold_label_affixed: false, other_action_taken: false, other_action_specify: "" },
                          })
                        }
                      >
                        + Add Equipment Impact
                      </button>
                    </>
                  );
                })()}
              </Field>

              <Field label="Immediate Actions">
                <StringListEditor
                  items={report.initial_impact_assessment.immediate_actions}
                  onChange={(v) => setListField("initial_impact_assessment", "immediate_actions", v)}
                />
              </Field>
                </>
              )}
            </SectionCard>

            {/* 4. History Review */}
            <SectionCard
              section={SECTIONS[3]}
              isOpen={!!openSections["history-review"]}
              onToggle={() => toggleSection("history-review")}
              editing={!!editSections["history-review"]}
              onToggleEdit={() => toggleEditSection("history-review")}
              read={!!readSections["history-review"]}
              onToggleRead={() => toggleReadSection("history-review")}
              setRef={(el) => (sectionRefs.current["history-review"] = el)}
            >
              {!report.history_review ? (
                <MissingFieldsNotice message={report.errors.history_review} />
              ) : (
                <>
              <Field label="Lookback Months">
                <TextInput
                  type="number"
                  value={String(report.history_review.lookback_months)}
                  onChange={(v) => setSectionField("history_review", "lookback_months", Number(v))}
                />
              </Field>
              <CheckboxField
                label="No Similar Events Found"
                checked={report.history_review.no_similar_events_found}
                onChange={(v) => setSectionField("history_review", "no_similar_events_found", v)}
              />
              {(() => {
                const list = report.history_review!.rows;
                const h = listHelpers<HistoryReviewRow>("history_review", "rows", list);
                const editing = editSections["history-review"];
                if (!editing) {
                  if (!list.length) return <ReadOnlyValue value="" />;
                  return (
                    <DataTable
                      columns={[
                        { key: "sl", label: "SL Number" },
                        { key: "event_number", label: "Event Number" },
                        { key: "event_title", label: "Event Title" },
                        { key: "capa_description", label: "CAPA Description" },
                        { key: "capa_implementation_date", label: "CAPA Implementation Date" },
                      ]}
                      rows={list.map((row, i) => ({ ...row, sl: i + 1 }))}
                    />
                  );
                }
                return (
                  <>
                    {list.map((row, i) => (
                      <div key={i} style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                        <Field label="Event Number">
                          <TextInput value={row.event_number} onChange={(v) => h.update(i, { event_number: v })} />
                        </Field>
                        <Field label="Event Title">
                          <TextInput value={row.event_title} onChange={(v) => h.update(i, { event_title: v })} />
                        </Field>
                        <Field label="CAPA Description">
                          <TextArea value={row.capa_description} rows={2} onChange={(v) => h.update(i, { capa_description: v })} />
                        </Field>
                        <Field label="CAPA Implementation Date">
                          <TextInput value={row.capa_implementation_date} onChange={(v) => h.update(i, { capa_implementation_date: v })} />
                        </Field>
                        <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => h.remove(i)}>
                          Remove
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      className="btn-outline"
                      style={{ alignSelf: "flex-start" }}
                      onClick={() => h.add({ event_number: "", event_title: "", capa_description: "", capa_implementation_date: "" })}
                    >
                      + Add Historic Event
                    </button>
                  </>
                );
              })()}
              <Field label="Closing Narrative">
                <TextArea value={report.history_review.closing_narrative} onChange={(v) => setSectionField("history_review", "closing_narrative", v)} />
              </Field>
              <Field label="Batches Manufactured Note (optional)">
                <TextInput
                  value={report.history_review.batches_manufactured_note ?? ""}
                  onChange={(v) => setSectionField("history_review", "batches_manufactured_note", v || null)}
                />
              </Field>
                </>
              )}
            </SectionCard>

            {/* 5. Investigation Task */}
            <SectionCard
              section={SECTIONS[4]}
              isOpen={!!openSections["investigation-task"]}
              onToggle={() => toggleSection("investigation-task")}
              editing={!!editSections["investigation-task"]}
              onToggleEdit={() => toggleEditSection("investigation-task")}
              read={!!readSections["investigation-task"]}
              onToggleRead={() => toggleReadSection("investigation-task")}
              setRef={(el) => (sectionRefs.current["investigation-task"] = el)}
            >
              {!report.investigation_task ? (
                <MissingFieldsNotice message={report.errors.investigation_task} />
              ) : (
                <>
              <Field label="RCA Method Evidence">
                <TextArea value={report.investigation_task.rca_method_evidence} onChange={(v) => setSectionField("investigation_task", "rca_method_evidence", v)} />
              </Field>
              <Field label="RCA Methods Used">
                <ChipMultiSelect<RCAMethod>
                  options={RCA_METHOD_OPTIONS}
                  selected={report.investigation_task.rca_methods_used}
                  onChange={(v) => setListField("investigation_task", "rca_methods_used", v)}
                />
              </Field>

              {(() => {
                const groups = report.investigation_task!.groups;
                const gh = listHelpers<InvestigationTaskGroup>("investigation_task", "groups", groups);
                const editing = editSections["investigation-task"];
                if (!editing) {
                  if (!groups.length) return <ReadOnlyValue value="" />;
                  return (
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      {groups.map((group, gi) => (
                        <div key={gi} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                          {group.section_title && <p style={{ margin: 0, fontWeight: 700 }}>{group.section_title}</p>}
                          {group.subsections.map((sub, si) => (
                            <div key={si} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                              <p style={READ_LABEL_STYLE}>{sub.title}</p>
                              {sub.six_m_factors.length > 0 && (
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                                  {sub.six_m_factors.map((f) => (
                                    <span key={f} style={{ fontSize: "var(--font-size-xs)", background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 6, padding: "2px 8px" }}>
                                      {f}
                                    </span>
                                  ))}
                                </div>
                              )}
                              {sub.findings.length > 0 && (
                                <ul style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 4 }}>
                                  {sub.findings.map((finding, fi) => (
                                    <li key={fi} style={{ fontSize: "var(--font-size-base)" }}>
                                      {finding.sop_reference && <strong>{finding.sop_reference}: </strong>}
                                      {finding.finding}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  );
                }
                return (
                  <>
                    {groups.map((group, gi) => {
                      const sh = {
                        add: (item: InvestigationTaskSubsection) => gh.update(gi, { subsections: [...group.subsections, item] }),
                        remove: (si: number) => gh.update(gi, { subsections: group.subsections.filter((_, j) => j !== si) }),
                        update: (si: number, patch: Partial<InvestigationTaskSubsection>) =>
                          gh.update(gi, { subsections: group.subsections.map((s, j) => (j === si ? { ...s, ...patch } : s)) }),
                      };
                      return (
                        <div key={gi} style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 10 }}>
                          <Field label="Group / Section Title">
                            <TextInput value={group.section_title} onChange={(v) => gh.update(gi, { section_title: v })} />
                          </Field>
                          {group.subsections.map((sub, si) => {
                            const fh = {
                              add: (item: InvestigationTaskFinding) => sh.update(si, { findings: [...sub.findings, item] }),
                              remove: (fi: number) => sh.update(si, { findings: sub.findings.filter((_, j) => j !== fi) }),
                              update: (fi: number, patch: Partial<InvestigationTaskFinding>) =>
                                sh.update(si, { findings: sub.findings.map((f, j) => (j === fi ? { ...f, ...patch } : f)) }),
                            };
                            return (
                              <div key={si} style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 8, background: "var(--color-bg)" }}>
                                <Field label="Subsection Title">
                                  <TextInput value={sub.title} onChange={(v) => sh.update(si, { title: v })} />
                                </Field>
                                <Field label="6M Factors">
                                  <ChipMultiSelect<SixMFactor> options={SIX_M_FACTOR_OPTIONS} selected={sub.six_m_factors} onChange={(v) => sh.update(si, { six_m_factors: v })} />
                                </Field>
                                {sub.findings.map((finding, fi) => (
                                  <div key={fi} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                                    <TextInput
                                      placeholder="SOP Reference (optional)"
                                      value={finding.sop_reference ?? ""}
                                      onChange={(v) => fh.update(fi, { sop_reference: v || null })}
                                      style={{ flex: "0 0 160px" }}
                                    />
                                    <TextArea
                                      placeholder="Finding"
                                      value={finding.finding}
                                      onChange={(v) => fh.update(fi, { finding: v })}
                                      style={{ flex: 1 }}
                                      rows={2}
                                    />
                                    <EditOnly>
                                      <button type="button" className="btn-outline" onClick={() => fh.remove(fi)}>
                                        Remove
                                      </button>
                                    </EditOnly>
                                  </div>
                                ))}
                                <EditOnly>
                                  <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => fh.add({ sop_reference: null, finding: "" })}>
                                    + Add Finding
                                  </button>
                                  <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => sh.remove(si)}>
                                    Remove Subsection
                                  </button>
                                </EditOnly>
                              </div>
                            );
                          })}
                          <EditOnly>
                            <button
                              type="button"
                              className="btn-outline"
                              style={{ alignSelf: "flex-start" }}
                              onClick={() => sh.add({ title: "", six_m_factors: [], findings: [] })}
                            >
                              + Add Subsection
                            </button>
                            <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => gh.remove(gi)}>
                              Remove Group
                            </button>
                          </EditOnly>
                        </div>
                      );
                    })}
                    <EditOnly>
                      <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => gh.add({ section_title: "", subsections: [] })}>
                        + Add Group
                      </button>
                    </EditOnly>
                  </>
                );
              })()}
                </>
              )}
            </SectionCard>

            {/* 6. Root Cause */}
            <SectionCard
              section={SECTIONS[5]}
              isOpen={!!openSections["root-cause"]}
              onToggle={() => toggleSection("root-cause")}
              editing={!!editSections["root-cause"]}
              onToggleEdit={() => toggleEditSection("root-cause")}
              read={!!readSections["root-cause"]}
              onToggleRead={() => toggleReadSection("root-cause")}
              setRef={(el) => (sectionRefs.current["root-cause"] = el)}
            >
              {!report.root_cause_conclusion ? (
                <MissingFieldsNotice message={report.errors.root_cause_conclusion} />
              ) : (
                <>
                  <Field label="Conclusion">
                    <TextArea value={report.root_cause_conclusion.conclusion} onChange={(v) => setSectionField("root_cause_conclusion", "conclusion", v)} />
                  </Field>
                  {editSections["root-cause"] ? (
                    <>
                      <Field label="Taxonomy — Category (6M)">
                        <SelectInput
                          value={report.root_cause_conclusion.taxonomy.category}
                          onChange={(v) => setNestedField("root_cause_conclusion", "taxonomy", { category: v })}
                          options={SIX_M_FACTOR_OPTIONS}
                        />
                      </Field>
                      <Field label="Taxonomy — Sub-Category">
                        <TextInput
                          value={report.root_cause_conclusion.taxonomy.sub_category}
                          onChange={(v) => setNestedField("root_cause_conclusion", "taxonomy", { sub_category: v })}
                        />
                      </Field>
                    </>
                  ) : (
                    <p style={{ margin: 0, fontSize: "var(--font-size-base)" }}>
                      Root cause – category: {report.root_cause_conclusion.taxonomy.category} &nbsp;&nbsp; Root cause – sub-category: {report.root_cause_conclusion.taxonomy.sub_category}
                    </p>
                  )}
                  <Field label="Repeat-Occurrence Evidence">
                    <TextArea
                      value={report.root_cause_conclusion.repeat_occurrence_evidence}
                      onChange={(v) => setSectionField("root_cause_conclusion", "repeat_occurrence_evidence", v)}
                    />
                  </Field>
                  <CheckboxField
                    label="Is Repeat Occurrence"
                    checked={report.root_cause_conclusion.is_repeat_occurrence}
                    onChange={(v) => setSectionField("root_cause_conclusion", "is_repeat_occurrence", v)}
                  />
                </>
              )}
            </SectionCard>

            {/* 7. Impact Assessment & Batch Disposition */}
            <SectionCard
              section={SECTIONS[6]}
              isOpen={!!openSections["impact-assessment-batch-disposition"]}
              onToggle={() => toggleSection("impact-assessment-batch-disposition")}
              editing={!!editSections["impact-assessment-batch-disposition"]}
              onToggleEdit={() => toggleEditSection("impact-assessment-batch-disposition")}
              read={!!readSections["impact-assessment-batch-disposition"]}
              onToggleRead={() => toggleReadSection("impact-assessment-batch-disposition")}
              setRef={(el) => (sectionRefs.current["impact-assessment-batch-disposition"] = el)}
            >
              {!report.impact_assessment_batch_disposition ? (
                <MissingFieldsNotice message={report.errors.impact_assessment_batch_disposition} />
              ) : (
                <>
              <ImpactSubsectionEditor
                label="Impact on Affected Batches"
                value={report.impact_assessment_batch_disposition.impact_on_affected_batches}
                onChange={(v) => setNestedField("impact_assessment_batch_disposition", "impact_on_affected_batches", v)}
                extra={(() => {
                  const list = report.impact_assessment_batch_disposition!.impact_on_affected_batches.batch_shipper_table;
                  const h = {
                    add: (item: BatchShipperImpact) =>
                      setNestedField("impact_assessment_batch_disposition", "impact_on_affected_batches", { batch_shipper_table: [...list, item] }),
                    remove: (i: number) =>
                      setNestedField("impact_assessment_batch_disposition", "impact_on_affected_batches", { batch_shipper_table: list.filter((_, j) => j !== i) }),
                    update: (i: number, patch: Partial<BatchShipperImpact>) =>
                      setNestedField("impact_assessment_batch_disposition", "impact_on_affected_batches", {
                        batch_shipper_table: list.map((it, j) => (j === i ? { ...it, ...patch } : it)),
                      }),
                  };
                  const editing = editSections["impact-assessment-batch-disposition"];
                  if (!editing) {
                    if (!list.length) return null;
                    return (
                      <DataTable
                        columns={[
                          { key: "batch_number", label: "Batch #" },
                          { key: "number_of_shippers", label: "Number of Shippers" },
                          { key: "defects", label: "Defects (if any)" },
                        ]}
                        rows={list}
                      />
                    );
                  }
                  return (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-sm)" }}>Batch / Shipper Table</p>
                      {list.map((row, i) => (
                        <div key={i} style={{ display: "flex", gap: 8 }}>
                          <TextInput placeholder="Batch Number" value={row.batch_number} onChange={(v) => h.update(i, { batch_number: v })} />
                          <TextInput placeholder="# Shippers" value={row.number_of_shippers} onChange={(v) => h.update(i, { number_of_shippers: v })} />
                          <TextInput placeholder="Defects" value={row.defects} onChange={(v) => h.update(i, { defects: v })} />
                          <button type="button" className="btn-outline" onClick={() => h.remove(i)}>
                            Remove
                          </button>
                        </div>
                      ))}
                      <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => h.add({ batch_number: "", number_of_shippers: "", defects: "None" })}>
                        + Add Batch/Shipper Row
                      </button>
                    </div>
                  );
                })()}
              />
              {IMPACT_SUBSECTION_FIELDS.map(({ key, label }) => (
                <ImpactSubsectionEditor
                  key={key}
                  label={label}
                  value={report.impact_assessment_batch_disposition![key] as ImpactSubsectionItem}
                  onChange={(v) => setNestedField("impact_assessment_batch_disposition", key as string, v)}
                />
              ))}
              <Field label="Conclusion">
                <TextArea value={report.impact_assessment_batch_disposition.conclusion} onChange={(v) => setSectionField("impact_assessment_batch_disposition", "conclusion", v)} />
              </Field>
              <Field label="Medical Investigation Summary (MC only)">
                <TextArea
                  value={report.impact_assessment_batch_disposition.medical_investigation_summary ?? ""}
                  onChange={(v) => setSectionField("impact_assessment_batch_disposition", "medical_investigation_summary", v || null)}
                />
              </Field>
              <Field label="Health Hazard Evaluation (MC only)">
                <TextArea
                  value={report.impact_assessment_batch_disposition.health_hazard_evaluation ?? ""}
                  onChange={(v) => setSectionField("impact_assessment_batch_disposition", "health_hazard_evaluation", v || null)}
                />
              </Field>
              <Field label="Impact Justification (OOS/OOT only)">
                <TextArea
                  value={report.impact_assessment_batch_disposition.impact_justification ?? ""}
                  onChange={(v) => setSectionField("impact_assessment_batch_disposition", "impact_justification", v || null)}
                />
              </Field>
                </>
              )}
            </SectionCard>

            {/* 8. Risk Assessment */}
            <SectionCard
              section={SECTIONS[7]}
              isOpen={!!openSections["risk-assessment"]}
              onToggle={() => toggleSection("risk-assessment")}
              editing={!!editSections["risk-assessment"]}
              onToggleEdit={() => toggleEditSection("risk-assessment")}
              read={!!readSections["risk-assessment"]}
              onToggleRead={() => toggleReadSection("risk-assessment")}
              setRef={(el) => (sectionRefs.current["risk-assessment"] = el)}
            >
              {!report.risk_assessment ? (
                <MissingFieldsNotice message={report.errors.risk_assessment} />
              ) : (
                <>
              <Field label="Applicability Reason">
                <TextArea value={report.risk_assessment.applicability_reason} onChange={(v) => setSectionField("risk_assessment", "applicability_reason", v)} />
              </Field>
              <Field label="Applicable">
                <SelectInput
                  value={report.risk_assessment.applicable}
                  onChange={(v) => setSectionField("risk_assessment", "applicable", v)}
                  options={["yes", "no — unconfirmed market complaint"] as const}
                />
              </Field>
              {(() => {
                const list = report.risk_assessment!.candidates;
                const h = listHelpers<RiskAssessmentCandidate>("risk_assessment", "candidates", list);
                const editing = editSections["risk-assessment"];
                if (!editing) {
                  if (!list.length) return <ReadOnlyValue value="" />;
                  return (
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 6, padding: "8px 12px", fontSize: "var(--font-size-sm)" }}>
                        <strong>RPN Formula:</strong> RPN = S &times; R &times; D <span style={{ color: "var(--color-text-muted)" }}>(S = Severity, R = Repeatability, D = Detectability)</span>
                      </div>
                      {list.map((c, i) => (
                        <div key={i} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                          <p style={{ margin: 0, fontWeight: 700 }}>{c.cause_label}</p>
                          <DataTable
                            columns={[
                              { key: "factor", label: "Factor" },
                              { key: "tier", label: "Tier" },
                              { key: "evidence", label: "Grounding Evidence" },
                              { key: "score", label: "Score" },
                            ]}
                            rows={(["severity", "repeatability", "detectability"] as const).map((factor) => ({
                              factor: factor[0].toUpperCase() + factor.slice(1),
                              tier: c.factors[factor].tier,
                              evidence: c.factors[factor].grounding_evidence,
                              score: factor === "severity" ? c.severity_score : factor === "repeatability" ? c.repeatability_score : c.detectability_score,
                            }))}
                          />
                          <p style={{ margin: 0, fontSize: "var(--font-size-sm)" }}>
                            <strong>RPN: {c.rpn}</strong> &middot; Risk level: {c.risk_level}
                          </p>
                        </div>
                      ))}
                    </div>
                  );
                }
                return (
                  <>
                    {list.map((c, i) => (
                      <div key={i} style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                        <Field label="Cause Label">
                          <TextInput value={c.cause_label} onChange={(v) => h.update(i, { cause_label: v })} />
                        </Field>
                        {(["severity", "repeatability", "detectability"] as const).map((factor) => (
                          <div key={factor} style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 8, background: "var(--color-bg)" }}>
                            <p style={{ margin: "0 0 6px", fontWeight: 600, fontSize: "var(--font-size-sm)", textTransform: "capitalize" }}>{factor}</p>
                            <Field label="Grounding Evidence">
                              <TextArea
                                rows={2}
                                value={c.factors[factor].grounding_evidence}
                                onChange={(v) =>
                                  h.update(i, { factors: { ...c.factors, [factor]: { ...c.factors[factor], grounding_evidence: v } } })
                                }
                              />
                            </Field>
                            <Field label="Tier">
                              <SelectInput
                                value={c.factors[factor].tier}
                                onChange={(v) => h.update(i, { factors: { ...c.factors, [factor]: { ...c.factors[factor], tier: v } } })}
                                options={
                                  factor === "severity"
                                    ? (["Critical", "Medium", "Low"] as const as readonly SeverityTier[])
                                    : (["High", "Medium", "Low"] as const as readonly (RepeatabilityTier | DetectabilityTier)[])
                                }
                              />
                            </Field>
                          </div>
                        ))}
                        <p style={{ margin: 0, fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
                          Severity score: {c.severity_score} · Repeatability score: {c.repeatability_score} · Detectability score: {c.detectability_score} · RPN:{" "}
                          {c.rpn} · Risk level: {c.risk_level} <em>(computed, not editable)</em>
                        </p>
                        <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => h.remove(i)}>
                          Remove
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      className="btn-outline"
                      style={{ alignSelf: "flex-start" }}
                      onClick={() =>
                        h.add({
                          cause_label: "",
                          factors: {
                            severity: { grounding_evidence: "", tier: "Low" },
                            repeatability: { grounding_evidence: "", tier: "Low" },
                            detectability: { grounding_evidence: "", tier: "Low" },
                          },
                          severity_score: 0,
                          repeatability_score: 0,
                          detectability_score: 0,
                          rpn: 0,
                          risk_level: "L1",
                        })
                        }
                      >
                        + Add Risk Candidate
                      </button>
                  </>
                );
              })()}
                </>
              )}
            </SectionCard>

            {/* 9. Correction & Remedial Action */}
            <SectionCard
              section={SECTIONS[8]}
              isOpen={!!openSections["correction-remedial-action"]}
              onToggle={() => toggleSection("correction-remedial-action")}
              editing={!!editSections["correction-remedial-action"]}
              onToggleEdit={() => toggleEditSection("correction-remedial-action")}
              read={!!readSections["correction-remedial-action"]}
              onToggleRead={() => toggleReadSection("correction-remedial-action")}
              setRef={(el) => (sectionRefs.current["correction-remedial-action"] = el)}
            >
              {!report.correction_remedial_action ? (
                <MissingFieldsNotice message={report.errors.correction_remedial_action} />
              ) : (
                <>
              {(() => {
                const list = report.correction_remedial_action!.items;
                const h = listHelpers<ObservationStatusItem>("correction_remedial_action", "items", list);
                const editing = editSections["correction-remedial-action"];
                if (!editing) {
                  if (!list.length) return <ReadOnlyValue value="" />;
                  return (
                    <DataTable
                      columns={[
                        { key: "observation", label: "Observation" },
                        { key: "status", label: "Status" },
                      ]}
                      rows={list}
                    />
                  );
                }
                return (
                  <>
                    {list.map((item, i) => (
                      <div key={i} style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                        <Field label="Observation">
                          <TextArea value={item.observation} rows={2} onChange={(v) => h.update(i, { observation: v })} />
                        </Field>
                        <Field label="Status">
                          <TextArea value={item.status} rows={2} onChange={(v) => h.update(i, { status: v })} />
                        </Field>
                        <Field label="Reference Number (optional)">
                          <TextInput value={item.reference_number ?? ""} onChange={(v) => h.update(i, { reference_number: v || null })} />
                        </Field>
                        <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => h.remove(i)}>
                          Remove
                        </button>
                      </div>
                    ))}
                    <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => h.add({ observation: "", status: "", reference_number: null })}>
                      + Add Observation
                    </button>
                  </>
                );
              })()}
              <Field label="Additional Notes">
                <StringListEditor items={report.correction_remedial_action.additional_notes} onChange={(v) => setListField("correction_remedial_action", "additional_notes", v)} />
              </Field>
                </>
              )}
            </SectionCard>

            {/* 10. CAPA */}
            <SectionCard
              section={SECTIONS[9]}
              isOpen={!!openSections["capa"]}
              onToggle={() => toggleSection("capa")}
              editing={!!editSections["capa"]}
              onToggleEdit={() => toggleEditSection("capa")}
              read={!!readSections["capa"]}
              onToggleRead={() => toggleReadSection("capa")}
              setRef={(el) => (sectionRefs.current["capa"] = el)}
            >
              {!report.capa ? (
                <MissingFieldsNotice message={report.errors.capa} />
              ) : (
                <>
              <Field label="CAPA Not Applicable Justification (optional)">
                <TextArea value={report.capa.capa_not_applicable_justification ?? ""} onChange={(v) => setSectionField("capa", "capa_not_applicable_justification", v || null)} />
              </Field>
              <Field label="CAPA Description / PR Number">
                {(() => {
                  const list = report.capa!.capa_actions;
                  const h = listHelpers<CAPAActionItem>("capa", "capa_actions", list);
                  const editing = editSections["capa"];
                  if (!editing) {
                    if (!list.length) return <ReadOnlyValue value="" />;
                    return (
                      <DataTable
                        columns={[
                          { key: "description", label: "CAPA Description / PR Number" },
                          { key: "responsibility", label: "Responsibility" },
                          { key: "due_date", label: "Due Date" },
                        ]}
                        rows={list.map((item) => ({ ...item, responsibility: item.responsibility ?? "" }))}
                      />
                    );
                  }
                  return (
                    <>
                      {list.map((item, i) => (
                        <div key={i} style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                          <Field label="Description">
                            <TextArea value={item.description} rows={2} onChange={(v) => h.update(i, { description: v })} />
                          </Field>
                          <Field label="Responsibility (optional)">
                            <TextInput value={item.responsibility ?? ""} onChange={(v) => h.update(i, { responsibility: v || null })} />
                          </Field>
                          <Field label="Due Date">
                            <TextInput value={item.due_date} onChange={(v) => h.update(i, { due_date: v })} />
                          </Field>
                          <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => h.remove(i)}>
                            Remove
                          </button>
                        </div>
                      ))}
                      <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => h.add({ description: "", responsibility: null, due_date: "" })}>
                        + Add CAPA Action
                      </button>
                    </>
                  );
                })()}
              </Field>
              <Field label="Interim Control Plan">
                {(() => {
                  const list = report.capa!.interim_controls;
                  const h = listHelpers<InterimControlItem>("capa", "interim_controls", list);
                  const editing = editSections["capa"];
                  if (!editing) {
                    if (!list.length) return <ReadOnlyValue value="" />;
                    return (
                      <DataTable
                        columns={[
                          { key: "description", label: "Interim Control Plan" },
                          { key: "responsibility", label: "Responsibility" },
                          { key: "due_date", label: "Due Date" },
                        ]}
                        rows={list}
                      />
                    );
                  }
                  return (
                    <>
                      {list.map((item, i) => (
                        <div key={i} style={{ display: "flex", gap: 8 }}>
                          <TextInput placeholder="Description" value={item.description} onChange={(v) => h.update(i, { description: v })} style={{ flex: 2 }} />
                          <TextInput placeholder="Responsibility" value={item.responsibility} onChange={(v) => h.update(i, { responsibility: v })} style={{ flex: 1 }} />
                          <TextInput placeholder="Due Date" value={item.due_date} onChange={(v) => h.update(i, { due_date: v })} style={{ flex: 1 }} />
                          <button type="button" className="btn-outline" onClick={() => h.remove(i)}>
                            Remove
                          </button>
                        </div>
                      ))}
                      <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => h.add({ description: "", responsibility: "", due_date: "" })}>
                        + Add Interim Control
                      </button>
                    </>
                  );
                })()}
              </Field>
              <p style={{ margin: 0, fontWeight: 600 }}>Extrapolation</p>
              <div style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                <CheckboxField
                  label="Applicable"
                  checked={report.capa.extrapolation.applicable}
                  onChange={(v) => setNestedField("capa", "extrapolation", { applicable: v })}
                />
                <Field label="Justification">
                  <TextArea value={report.capa.extrapolation.justification} onChange={(v) => setNestedField("capa", "extrapolation", { justification: v })} />
                </Field>
                <Field label="Scope Description">
                  <TextArea value={report.capa.extrapolation.scope_description} onChange={(v) => setNestedField("capa", "extrapolation", { scope_description: v })} />
                </Field>
                <Field label="Related Customers">
                  <StringListEditor items={report.capa.extrapolation.related_customers} onChange={(v) => setNestedField("capa", "extrapolation", { related_customers: v })} />
                </Field>
                <Field label="Related Markets">
                  <StringListEditor items={report.capa.extrapolation.related_markets} onChange={(v) => setNestedField("capa", "extrapolation", { related_markets: v })} />
                </Field>
                <Field label="CAPA Numbers">
                  <StringListEditor items={report.capa.extrapolation.capa_numbers} onChange={(v) => setNestedField("capa", "extrapolation", { capa_numbers: v })} />
                </Field>
                <Field label="Related Change Controls">
                  <StringListEditor items={report.capa.extrapolation.related_change_controls} onChange={(v) => setNestedField("capa", "extrapolation", { related_change_controls: v })} />
                </Field>
                <Field label="Responsibility">
                  <TextInput value={report.capa.extrapolation.responsibility} onChange={(v) => setNestedField("capa", "extrapolation", { responsibility: v })} />
                </Field>
                <Field label="Due Date">
                  <TextInput value={report.capa.extrapolation.due_date} onChange={(v) => setNestedField("capa", "extrapolation", { due_date: v })} />
                </Field>
              </div>
                </>
              )}
            </SectionCard>

            {/* 11. CAPA Effectiveness Check Plan */}
            <SectionCard
              section={SECTIONS[10]}
              isOpen={!!openSections["capa-effectiveness-check-plan"]}
              onToggle={() => toggleSection("capa-effectiveness-check-plan")}
              editing={!!editSections["capa-effectiveness-check-plan"]}
              onToggleEdit={() => toggleEditSection("capa-effectiveness-check-plan")}
              read={!!readSections["capa-effectiveness-check-plan"]}
              onToggleRead={() => toggleReadSection("capa-effectiveness-check-plan")}
              setRef={(el) => (sectionRefs.current["capa-effectiveness-check-plan"] = el)}
            >
              {!report.capa_effectiveness_check_plan ? (
                <MissingFieldsNotice message={report.errors.capa_effectiveness_check_plan} />
              ) : (
                <>
              <Field label="CAPA Not Applicable Justification (optional)">
                <TextArea
                  value={report.capa_effectiveness_check_plan.capa_not_applicable_justification ?? ""}
                  onChange={(v) => setSectionField("capa_effectiveness_check_plan", "capa_not_applicable_justification", v || null)}
                />
              </Field>
              {(() => {
                const list = report.capa_effectiveness_check_plan!.generated_plans;
                const h = listHelpers<CAPAEffectivenessPlanItem>("capa_effectiveness_check_plan", "generated_plans", list);
                const editing = editSections["capa-effectiveness-check-plan"];
                const bullets = (items: string[]) => (
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {items.map((it, i) => (
                      <li key={i}>{it}</li>
                    ))}
                  </ul>
                );
                if (!editing) {
                  if (!list.length) return <ReadOnlyValue value="" />;
                  return (
                    <DataTable
                      columns={[
                        { key: "capa_description", label: "CAPA Description" },
                        { key: "effectiveness_check", label: "Effectiveness Check" },
                        { key: "effectiveness_criteria", label: "Effectiveness Criteria" },
                        { key: "responsibility", label: "Responsibility" },
                        { key: "monitoring_duration", label: "Monitoring Duration" },
                      ]}
                      rows={list.map((item) => ({
                        ...item,
                        _cell: (key: string) =>
                          key === "effectiveness_check" ? bullets(item.effectiveness_check) : key === "effectiveness_criteria" ? bullets(item.effectiveness_criteria) : undefined,
                      }))}
                    />
                  );
                }
                return (
                  <>
                    {list.map((item, i) => (
                      <div key={i} style={{ border: "1px solid var(--color-card-border)", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                        <Field label="Grounding Evidence">
                          <TextArea value={item.grounding_evidence} onChange={(v) => h.update(i, { grounding_evidence: v })} />
                        </Field>
                        <Field label="CAPA Mechanism">
                          <SelectInput value={item.capa_mechanism} onChange={(v) => h.update(i, { capa_mechanism: v })} options={CAPA_MECHANISM_OPTIONS} />
                        </Field>
                        <Field label="CAPA Description">
                          <TextArea value={item.capa_description} onChange={(v) => h.update(i, { capa_description: v })} />
                        </Field>
                        <Field label="Effectiveness Check (bullets)">
                          <StringListEditor items={item.effectiveness_check} onChange={(v) => h.update(i, { effectiveness_check: v })} />
                        </Field>
                        <Field label="Effectiveness Criteria (bullets)">
                          <StringListEditor items={item.effectiveness_criteria} onChange={(v) => h.update(i, { effectiveness_criteria: v })} />
                        </Field>
                        <Field label="Responsibility">
                          <TextInput value={item.responsibility} onChange={(v) => h.update(i, { responsibility: v })} />
                        </Field>
                        <Field label="Duration Rationale">
                          <TextArea value={item.duration_rationale} onChange={(v) => h.update(i, { duration_rationale: v })} />
                        </Field>
                        <Field label="Duration Tier">
                          <SelectInput value={item.duration_tier} onChange={(v) => h.update(i, { duration_tier: v })} options={DURATION_TIER_OPTIONS} />
                        </Field>
                        <Field label="Monitoring Duration">
                          <TextInput value={item.monitoring_duration} onChange={(v) => h.update(i, { monitoring_duration: v })} />
                        </Field>
                        <EditOnly>
                          <button type="button" className="btn-outline" style={{ alignSelf: "flex-start" }} onClick={() => h.remove(i)}>
                            Remove
                          </button>
                        </EditOnly>
                      </div>
                    ))}
                    <EditOnly>
                    <button
                      type="button"
                      className="btn-outline"
                      style={{ alignSelf: "flex-start" }}
                      onClick={() =>
                        h.add({
                          grounding_evidence: "",
                          capa_mechanism: "Procedural / training-based",
                          capa_description: "",
                          effectiveness_check: [],
                          effectiveness_criteria: [],
                          responsibility: "",
                          duration_rationale: "",
                          duration_tier: "standard",
                          monitoring_duration: "",
                        })
                      }
                    >
                      + Add Effectiveness Plan
                    </button>
                    </EditOnly>
                  </>
                );
              })()}
                </>
              )}
            </SectionCard>
          </div>
        </>
      )}
    </div>
  );
}
