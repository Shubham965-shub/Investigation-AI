import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  exportRciPlanDocx,
  generateRciPlan,
  getOpenInvestigators,
  getProblemStatementRecord,
  getRciPlanRecord,
  updateRciPlanSections,
  type RciSectionItem,
} from "../api/dashboard";
import { ApiError } from "../api/client";
import { getAdditionalFieldsForModule, type EventType, type TrackwiseFields } from "../constants/trackwiseFields";
import { DbErrorModal } from "../components/DbErrorModal";
import { ConfirmDialog } from "../components/ConfirmDialog";
import rowChevronIcon from "../assets/icons/rci-row-chevron.svg";
import exportIcon from "../assets/icons/rci-export-icon.svg";
import penIcon from "../assets/icons/rci-pen-icon.svg";
import checkIcon from "../assets/icons/evidence-checkbox.svg";
import "./RecordModulePage.css";

// TCD (target completion date) must be a future date — per the user
// (2026-07-31), the calendar picker should only allow dates after today, so
// this is used as the <input type="date">'s min (exclusive of today itself).
function tomorrowIso(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

// due_date is always a plain "yyyy-mm-dd" string (native <input type="date">'s
// value format) — displayed as dd/mm/yyyy once locked/read-only (2026-08-18,
// per the user). The editable native date input itself still renders
// according to the browser's own locale — that's outside app-level control.
function formatDdMmYyyy(iso: string): string {
  const [y, m, d] = iso.split("-");
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

export function RciPlanPage() {
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();
  const persistTimerRef = useRef<number | null>(null);
  const minDueDate = useMemo(() => tomorrowIso(), []);

  const [recordLoading, setRecordLoading] = useState(true);
  const [dbError, setDbError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [problemStatement, setProblemStatement] = useState<string | null>(null);
  // True once Task Critique has started on any section — RCI Plan becomes
  // read-only at that point (2026-08-05, per the user), since editing here
  // would delete-then-recreate section rows and cascade away that history.
  const [lockedForEditing, setLockedForEditing] = useState(false);
  const [eventType, setEventType] = useState<EventType | undefined>(undefined);
  const [trackwiseFields, setTrackwiseFields] = useState<TrackwiseFields | undefined>(undefined);
  const [sections, setSections] = useState<RciSectionItem[] | null>(null);
  const [openSections, setOpenSections] = useState<Record<number, boolean>>({});
  // Toggled by the header "Edit" button (previously cosmetic/disabled) —
  // reveals an "Add Task" row at the bottom of each open section's task
  // list. Scoped to just adding subtasks for now, per the user (2026-08-05);
  // editing existing task text/checking is already possible without this.
  const [editMode, setEditMode] = useState(false);
  // Per-section draft text for the new-task input, keyed by section index —
  // each section's "Add Task" row needs its own independent in-progress text.
  const [newTaskDrafts, setNewTaskDrafts] = useState<Record<number, string>>({});
  const [additionalValues, setAdditionalValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [pushed, setPushed] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [investigators, setInvestigators] = useState<string[]>([]);

  // Everything comes from the DB — no localStorage. RCI Plan depends on the
  // Problem Statement record existing (fetched here directly rather than
  // assumed from a prior page visit), plus its own record for
  // event_type/trackwise_fields/already-generated plan. A 404 on either is a
  // valid "not generated/no record yet" state; any other failure blocks the
  // page via DbErrorModal.
  useEffect(() => {
    if (!recordId) return;
    let cancelled = false;
    setRecordLoading(true);
    setDbError(null);
    (async () => {
      try {
        const [psRecord, rciRecord, investigatorNames] = await Promise.all([
          getProblemStatementRecord(recordId),
          getRciPlanRecord(recordId),
          getOpenInvestigators(),
        ]);
        if (cancelled) return;
        setProblemStatement(psRecord?.problem_statement ?? null);
        setInvestigators(investigatorNames);
        if (rciRecord) {
          setEventType(rciRecord.event_type);
          setTrackwiseFields(rciRecord.trackwise_fields);
          setLockedForEditing(rciRecord.locked_for_editing ?? false);
          if (rciRecord.sections) {
            setSections(rciRecord.sections);
          }
          // The GET response's trackwise_fields already includes the
          // extended field set (Deviation Number, Date Opened, etc.) — pull
          // those straight from the backend instead of leaving the
          // "Additional Details" inputs blank for the user to retype.
          const fieldsNeeded = getAdditionalFieldsForModule("rci-plan", rciRecord.event_type);
          const prefill: Record<string, string> = {};
          for (const field of fieldsNeeded) {
            const value = rciRecord.trackwise_fields[field.key];
            // "list"-kind fields (Immediate Actions, Impact Details, Proposal
            // for Resolution) come back as arrays — join with "\n" to match
            // the same one-per-line textarea convention handleGenerate's
            // split("\n") expects on submit, instead of dropping the field
            // (typeof value === "string" alone would silently leave it
            // blank, same class of bug as Related Market/Related Customer).
            if (typeof value === "string") prefill[field.key] = value;
            else if (Array.isArray(value)) prefill[field.key] = value.join("\n");
          }
          setAdditionalValues(prefill);
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

  const additionalFields = useMemo(
    () => (eventType ? getAdditionalFieldsForModule("rci-plan", eventType) : []),
    [eventType]
  );

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

  if (!problemStatement || !eventType || !trackwiseFields) {
    return (
      <div className="empty-state">
        <p>Complete the Problem Statement step first — RCI Plan needs it to generate a plan.</p>
        <button type="button" className="btn-primary" onClick={() => navigate(`/records/${recordId}/problem-statement`)}>
          Go to Problem Statement
        </button>
      </div>
    );
  }

  async function handleGenerate() {
    setError(null);
    setLoading(true);
    try {
      // DS's schema requires every "list"-kind field (Immediate Actions,
      // Impact Details, Proposal for Resolution) as an actual array, not a
      // string — split each "one per line" text value on newlines. Also
      // make sure every additional field key is present in the payload even
      // if the user never touched it (e.g. "Equipment Number" has no real
      // data source since that DB column was dropped) — DS rejects the
      // request outright if a required key is missing entirely.
      const mergedFields: TrackwiseFields = { ...trackwiseFields };
      for (const field of additionalFields) {
        const raw = additionalValues[field.key] ?? "";
        mergedFields[field.key] =
          field.kind === "list"
            ? raw.split("\n").map((line) => line.trim()).filter(Boolean)
            : raw;
      }
      const response = await generateRciPlan(recordId!, { event_type: eventType!, trackwise_fields: mergedFields });
      // Session-only display — the backend persists this (best-effort) as
      // part of the generate call.
      setSections(response.sections);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Failed to generate RCI plan");
    } finally {
      setLoading(false);
    }
  }

  function toggleSection(index: number) {
    setOpenSections((prev) => ({ ...prev, [index]: !prev[index] }));
  }

  // Persisted best-effort, debounced 600ms after the last edit — typing in
  // the investigator field fired a full replace-all-sections PUT on every
  // keystroke, which (combined with a since-fixed backend race — see
  // replace_rci_sections) produced duplicated sections with different
  // partially-typed substrings of "Unassigned" as the assignee. The backend
  // fix alone prevents the corruption; debouncing here also cuts the sheer
  // number of full-replace round-trips a fast typist fires.
  function persistSections(list: RciSectionItem[]) {
    if (!recordId) return;
    if (persistTimerRef.current) window.clearTimeout(persistTimerRef.current);
    persistTimerRef.current = window.setTimeout(() => {
      updateRciPlanSections(recordId, list).catch((err) => {
        console.error("Failed to persist RCI plan sections", err);
      });
    }, 600);
  }

  function toggleSectionIncluded(index: number) {
    if (!sections) return;
    const newSections = sections.map((s, i) => (i === index ? { ...s, is_checked: !(s.is_checked ?? true) } : s));
    setSections(newSections);
    persistSections(newSections);
  }

  function addSection() {
    if (!sections) return;
    const newSection: RciSectionItem = { title: "", correlation: null, assignee: null, due_date: null, tasks: [] };
    const newSections = [...sections, newSection];
    setSections(newSections);
    persistSections(newSections);
    // Open it immediately so the new (blank) title/correlation inputs are
    // visible to fill in right away, same as landing on any other section.
    setOpenSections((prev) => ({ ...prev, [newSections.length - 1]: true }));
  }

  function setSectionTitle(index: number, title: string) {
    if (!sections) return;
    const newSections = sections.map((s, i) => (i === index ? { ...s, title } : s));
    setSections(newSections);
    persistSections(newSections);
  }

  function setSectionCorrelation(index: number, correlation: string) {
    if (!sections) return;
    const newSections = sections.map((s, i) => (i === index ? { ...s, correlation: correlation || null } : s));
    setSections(newSections);
    persistSections(newSections);
  }

  function setSectionAssignee(index: number, assignee: string | null) {
    if (!sections) return;
    const newSections = sections.map((s, i) => (i === index ? { ...s, assignee } : s));
    setSections(newSections);
    persistSections(newSections);
  }

  function setSectionDueDate(index: number, dueDate: string) {
    if (!sections) return;
    const newSections = sections.map((s, i) => (i === index ? { ...s, due_date: dueDate || null } : s));
    setSections(newSections);
    persistSections(newSections);
  }

  function toggleTask(sectionIndex: number, taskIndex: number) {
    if (!sections) return;
    const newSections = sections.map((s, si) => {
      if (si !== sectionIndex) return s;
      const tasks = s.tasks.map((t, ti) => (ti === taskIndex ? { ...t, is_checked: !(t.is_checked ?? true) } : t));
      return { ...s, tasks };
    });
    setSections(newSections);
    persistSections(newSections);
  }

  function setTaskDescription(sectionIndex: number, taskIndex: number, description: string) {
    if (!sections) return;
    const newSections = sections.map((s, si) => {
      if (si !== sectionIndex) return s;
      const tasks = s.tasks.map((t, ti) => (ti === taskIndex ? { ...t, description } : t));
      return { ...s, tasks };
    });
    setSections(newSections);
    persistSections(newSections);
  }

  function addTask(sectionIndex: number) {
    if (!sections) return;
    const description = (newTaskDrafts[sectionIndex] ?? "").trim();
    if (!description) return;
    const newSections = sections.map((s, si) =>
      si === sectionIndex ? { ...s, tasks: [...s.tasks, { description, is_checked: true }] } : s
    );
    setSections(newSections);
    persistSections(newSections);
    setNewTaskDrafts((prev) => ({ ...prev, [sectionIndex]: "" }));
  }

  // Real .docx download — the backend fills the company's actual RCI Plan
  // Word template (assets/rci_plan_template.docx) with this investigation's
  // persisted sections and returns the file directly.
  async function downloadRciPlanDocument() {
    if (!recordId) return;
    const blob = await exportRciPlanDocx(recordId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `RCI_Plan_${recordId}.docx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  // Every task needs both an investigator and a TCD before the plan can be
  // pushed to Trackwise / proceed to Task Critique (2026-08-16, per the
  // user) — checked across every section, not just the ones with real
  // checklist items, since the assignee/TCD fields are always shown.
  // Excluded sections don't need an assignee/TCD — they're being left out of
  // the final plan entirely (2026-08-20, per the user).
  const missingAssignments = (sections ?? []).some((s) => (s.is_checked ?? true) && (!s.assignee || !s.due_date));

  async function handleAcceptAndPush() {
    if (missingAssignments) return;
    setShowConfirm(false);
    setExportError(null);
    try {
      await downloadRciPlanDocument();
      setPushed(true);
      setTimeout(() => navigate(`/records/${recordId}/task-critique`), 1500);
    } catch (err) {
      setExportError(err instanceof ApiError ? String(err.detail) : "Failed to export the RCI plan document");
    }
  }

  if (!sections) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="card">
          <p className="card-title">Problem Statement</p>
          <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12 }}>
            <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-md)", lineHeight: 1.9 }}>{problemStatement}</p>
          </div>
        </div>

        {error && <p className="error-banner">{error}</p>}

        <div className="footer-actions">
          <button type="button" className="btn-primary" onClick={handleGenerate} disabled={loading}>
            {loading ? "Generating…" : "Generate RCI Plan"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card">
        <p className="card-title">Problem Statement</p>
        <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12 }}>
          <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-md)", lineHeight: 1.9 }}>{problemStatement}</p>
        </div>
      </div>

      <div className="card-header">
        <p className="card-title">RCI Plan</p>
        {!lockedForEditing && (
          <button
            type="button"
            className="btn-outline"
            style={{ padding: 8, background: editMode ? "var(--color-rail-active-bg)" : undefined }}
            aria-label={editMode ? "Done adding tasks" : "Add tasks"}
            title={editMode ? "Done adding tasks" : "Add tasks to a section"}
            onClick={() => setEditMode((prev) => !prev)}
          >
            <img src={penIcon} alt="" width={16} height={16} />
          </button>
        )}
      </div>
      {lockedForEditing && (
        <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-text-muted)" }}>
          This RCI Plan is read-only — Task Critique has already started on it.
        </p>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {sections.map((section, index) => {
          const isOpen = !!openSections[index];
          const included = section.is_checked ?? true;
          return (
            <div key={index} className="card" style={{ gap: 12, opacity: included ? 1 : 0.6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <button
                  type="button"
                  className={`checklist-checkbox ${included ? "" : "unchecked"}`}
                  onClick={lockedForEditing ? undefined : () => toggleSectionIncluded(index)}
                  aria-label={included ? "Exclude section from final plan" : "Include section in final plan"}
                  title={included ? "Exclude from final plan" : "Include in final plan"}
                  style={{ flexShrink: 0, cursor: lockedForEditing ? "default" : "pointer" }}
                  disabled={lockedForEditing}
                >
                  {included && <img src={checkIcon} alt="" width={12} height={12} />}
                </button>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {editMode && !lockedForEditing ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <span style={{ fontWeight: 600, fontSize: "var(--font-size-base)", flexShrink: 0 }}>{index + 1}.</span>
                        <input
                          type="text"
                          value={section.title}
                          onChange={(e) => setSectionTitle(index, e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          style={{ fontWeight: 600, fontSize: "var(--font-size-base)", border: "1px solid var(--color-card-border)", borderRadius: "var(--radius-btn)", background: "var(--color-bg)", flex: 1, minWidth: 0, padding: "4px 8px" }}
                        />
                        <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)", flexShrink: 0 }}>({section.tasks.length} {section.tasks.length === 1 ? "task" : "tasks"})</span>
                      </div>
                      <input
                        type="text"
                        placeholder="Correlation (optional)"
                        value={section.correlation ?? ""}
                        onChange={(e) => setSectionCorrelation(index, e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        style={{ fontSize: "var(--font-size-base)", color: "var(--color-text-faint)", border: "1px solid var(--color-card-border)", borderRadius: "var(--radius-btn)", background: "var(--color-bg)", padding: "4px 8px" }}
                      />
                    </div>
                  ) : (
                    <>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <span style={{ fontWeight: 600, fontSize: "var(--font-size-base)" }}>
                          {index + 1}. {section.title}
                        </span>
                        <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>({section.tasks.length} {section.tasks.length === 1 ? "task" : "tasks"})</span>
                      </div>
                      {section.correlation && (
                        <p style={{ margin: "2px 0 0", fontSize: "var(--font-size-base)", color: "var(--color-text-faint)" }}>{section.correlation}</p>
                      )}
                    </>
                  )}
                </div>
                <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", display: "flex", alignItems: "center", gap: 6, fontSize: "var(--font-size-md)", color: "var(--color-text-faint)", minWidth: 200, boxSizing: "border-box" }}>
                  <span>TCD:</span>
                  {lockedForEditing ? (
                    <span>{section.due_date ? formatDdMmYyyy(section.due_date) : "—"}</span>
                  ) : (
                    <input
                      type="date"
                      min={minDueDate}
                      value={section.due_date ?? ""}
                      onChange={(e) => setSectionDueDate(index, e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      style={{ border: "none", background: "none", fontSize: "var(--font-size-md)", color: "var(--color-text-faint)", padding: 0 }}
                    />
                  )}
                </div>
                <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: lockedForEditing ? "9px 13px" : "5px 7px", display: "flex", alignItems: "center", gap: 8, minWidth: 200, boxSizing: "border-box" }}>
                  {lockedForEditing ? (
                    <span style={{ fontSize: "var(--font-size-md)", color: "var(--color-text-faint)" }}>{section.assignee || "Unassigned"}</span>
                  ) : (
                    <select
                      value={section.assignee ?? ""}
                      onChange={(e) => setSectionAssignee(index, e.target.value || null)}
                      onClick={(e) => e.stopPropagation()}
                      style={{ fontSize: "var(--font-size-md)", color: "var(--color-text-faint)", border: "none", background: "none", flex: 1, width: "100%", minWidth: 0, padding: "6px 8px", boxSizing: "border-box" }}
                    >
                      <option value="">Unassigned</option>
                      {section.assignee && !investigators.includes(section.assignee) && (
                        <option value={section.assignee}>{section.assignee}</option>
                      )}
                      {investigators.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => toggleSection(index)}
                  style={{ background: "none", border: "none" }}
                  aria-label="Toggle tasks"
                >
                  <img src={rowChevronIcon} alt="" width={24} height={24} style={{ transform: isOpen ? "rotate(0deg)" : "rotate(180deg)" }} />
                </button>
              </div>
              {isOpen && (
                <div style={{ border: "1px solid var(--color-card-border)", borderRadius: 4, overflow: "hidden" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", background: "var(--color-bg)", borderBottom: "1px solid var(--color-card-border)", padding: "8px 16px", fontSize: "var(--font-size-sm)", fontWeight: 600, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: 0.3 }}>
                    <span style={{ width: "100%" }}>Task</span>
                  </div>
                  {section.tasks.map((task, taskIndex) => {
                    const checked = task.is_checked ?? true;
                    return (
                      <div
                        key={taskIndex}
                        style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "8px 16px", borderBottom: taskIndex < section.tasks.length - 1 ? "1px solid var(--color-card-border)" : "none" }}
                      >
                        <div style={{ display: "flex", alignItems: "flex-start", gap: 10, width: "100%" }}>
                          <button
                            type="button"
                            className={`checklist-checkbox ${checked ? "" : "unchecked"}`}
                            onClick={lockedForEditing ? undefined : () => toggleTask(index, taskIndex)}
                            aria-label={checked ? "Uncheck task" : "Check task"}
                            style={{ flexShrink: 0, marginTop: 2, cursor: lockedForEditing ? "default" : "pointer" }}
                            disabled={lockedForEditing}
                          >
                            {checked && <img src={checkIcon} alt="" width={12} height={12} />}
                          </button>
                          {lockedForEditing ? (
                            <span style={{ fontSize: "var(--font-size-base)", fontWeight: 600, color: "var(--color-text-muted)", flex: 1, minWidth: 0, whiteSpace: "pre-wrap", overflowWrap: "break-word" }}>
                              {task.description}
                            </span>
                          ) : (
                            <textarea
                              value={task.description}
                              onChange={(e) => setTaskDescription(index, taskIndex, e.target.value)}
                              rows={1}
                              ref={(el) => {
                                if (!el) return;
                                el.style.height = "auto";
                                el.style.height = `${el.scrollHeight}px`;
                              }}
                              style={{
                                fontSize: "var(--font-size-base)",
                                fontWeight: 600,
                                fontFamily: "inherit",
                                color: "var(--color-text-muted)",
                                border: "none",
                                background: "none",
                                flex: 1,
                                minWidth: 0,
                                padding: 0,
                                resize: "none",
                                overflow: "hidden",
                                whiteSpace: "pre-wrap",
                                overflowWrap: "break-word",
                              }}
                            />
                          )}
                        </div>
                      </div>
                    );
                  })}
                  {editMode && !lockedForEditing && (
                    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 16px", borderTop: section.tasks.length > 0 ? "1px solid var(--color-card-border)" : "none" }}>
                      <input
                        type="text"
                        placeholder="Add a task…"
                        value={newTaskDrafts[index] ?? ""}
                        onChange={(e) => setNewTaskDrafts((prev) => ({ ...prev, [index]: e.target.value }))}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            addTask(index);
                          }
                        }}
                        style={{ fontSize: "var(--font-size-base)", color: "var(--color-text-muted)", border: "1px solid var(--color-card-border)", borderRadius: "var(--radius-btn)", background: "var(--color-bg)", flex: 1, padding: "6px 10px" }}
                      />
                      <button
                        type="button"
                        className="btn-outline"
                        onClick={() => addTask(index)}
                        disabled={!(newTaskDrafts[index] ?? "").trim()}
                      >
                        Add
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {editMode && !lockedForEditing && (
        <button type="button" className="btn-outline" onClick={addSection} style={{ alignSelf: "flex-start" }}>
          Add Task
        </button>
      )}

      {exportError && <p className="error-banner">{exportError}</p>}
      {missingAssignments && (
        <p style={{ margin: 0, fontSize: "var(--font-size-base)", color: "var(--color-warning-text)" }}>
          Every task needs an Investigator and a TCD (due date) assigned before the RCI Plan can be pushed to Trackwise.
        </p>
      )}

      <div className="footer-actions">
        <button
          type="button"
          className="btn-primary"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            opacity: missingAssignments ? 0.4 : 1,
            cursor: missingAssignments ? "default" : "pointer",
          }}
          disabled={missingAssignments}
          onClick={() => setShowConfirm(true)}
        >
          <img src={exportIcon} alt="" width={16} height={16} />
          {pushed ? "Pushed — downloading…" : "Accept and Push for SIT Review"}
        </button>
      </div>

      {showConfirm && (
        <ConfirmDialog
          title="Accept RCI Plan?"
          message="Are you sure you want to accept the RCI Plan and push it to Trackwise? The generated document will be downloaded to your device."
          onCancel={() => setShowConfirm(false)}
          onConfirm={handleAcceptAndPush}
        />
      )}
    </div>
  );
}
