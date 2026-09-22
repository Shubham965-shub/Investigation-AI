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
import { getEventExplorerHandoffUrl } from "../api/auth";
import { getAdditionalFieldsForModule, type EventType, type TrackwiseFields } from "../constants/trackwiseFields";
import { DbErrorModal } from "../components/DbErrorModal";
import { ConfirmDialog } from "../components/ConfirmDialog";
import rowChevronIcon from "../assets/icons/rci-row-chevron.svg";
import exportIcon from "../assets/icons/rci-export-icon.svg";
import penIcon from "../assets/icons/rci-pen-icon.svg";
import checkIcon from "../assets/icons/evidence-checkbox.svg";
import "./RecordModulePage.css";

// TCD must be a future date — used as the <input type="date">'s min (exclusive of today).
function tomorrowIso(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

// Default Target Date: today + 5 working days (weekends skipped, today not counted) — always later than tomorrowIso()'s min.
function defaultDueDateIso(): string {
  const d = new Date();
  let remaining = 5;
  while (remaining > 0) {
    d.setDate(d.getDate() + 1);
    const day = d.getDay(); // 0 = Sunday, 6 = Saturday
    if (day !== 0 && day !== 6) remaining -= 1;
  }
  return d.toISOString().slice(0, 10);
}

// due_date is a plain "yyyy-mm-dd" string — displayed as dd/mm/yyyy once locked/read-only; the editable input itself follows the browser's own locale.
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
  // True once Task Critique has started on any section — RCI Plan becomes read-only since editing would delete-then-recreate rows and lose that history.
  const [lockedForEditing, setLockedForEditing] = useState(false);
  const [eventType, setEventType] = useState<EventType | undefined>(undefined);
  const [trackwiseFields, setTrackwiseFields] = useState<TrackwiseFields | undefined>(undefined);
  const [sections, setSections] = useState<RciSectionItem[] | null>(null);
  const [openSections, setOpenSections] = useState<Record<number, boolean>>({});
  // Toggled by the header "Edit" button — gates every edit affordance in the plan; edits must only be possible in edit mode.
  const [editMode, setEditMode] = useState(false);
  // Per-section draft text for the new-task input, keyed by section index.
  const [newTaskDrafts, setNewTaskDrafts] = useState<Record<number, string>>({});
  const [additionalValues, setAdditionalValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [pushed, setPushed] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  // Surfaces a persistSections failure — without this the optimistic setSections() update still looked saved even when the backend call failed.
  const [persistError, setPersistError] = useState<string | null>(null);
  const [investigators, setInvestigators] = useState<string[]>([]);
  // "Explore Events" lives only on this page's Problem Statement card.
  const [exploreEventsError, setExploreEventsError] = useState<string | null>(null);

  // Depends on the Problem Statement record existing — a 404 on either fetch is a valid "not generated yet" state; any other failure blocks the page via DbErrorModal.
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
            // Backfills a Target Date for plans generated before this default existed — skipped once the plan is locked.
            const filled = rciRecord.sections.map((s) => (s.due_date ? s : { ...s, due_date: defaultDueDateIso() }));
            setSections(filled);
            if (!rciRecord.locked_for_editing && filled.some((s, i) => s.due_date !== rciRecord.sections![i].due_date)) {
              persistSections(filled);
            }
          }
          // Prefill "Additional Details" from the backend's trackwise_fields instead of leaving them blank to retype.
          const fieldsNeeded = getAdditionalFieldsForModule("rci-plan", rciRecord.event_type);
          const prefill: Record<string, string> = {};
          for (const field of fieldsNeeded) {
            const value = rciRecord.trackwise_fields[field.key];
            // "list"-kind fields come back as arrays — join with "\n" to match handleGenerate's split("\n") convention, instead of silently dropping them.
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
      // DS requires "list"-kind fields as real arrays (split on newlines) and every additional field key present even if untouched, or it rejects the request.
      const mergedFields: TrackwiseFields = { ...trackwiseFields };
      for (const field of additionalFields) {
        const raw = additionalValues[field.key] ?? "";
        mergedFields[field.key] =
          field.kind === "list"
            ? raw.split("\n").map((line) => line.trim()).filter(Boolean)
            : raw;
      }
      const response = await generateRciPlan(recordId!, { event_type: eventType!, trackwise_fields: mergedFields });
      // Defaults each generated section's Target Date to today + 5 working days instead of leaving it blank; still freely editable after.
      const filled = response.sections.map((s) => (s.due_date ? s : { ...s, due_date: defaultDueDateIso() }));
      setSections(filled);
      // The generate call's own persist ran before this default was computed — push it through the normal persist path too.
      persistSections(filled);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Failed to generate RCI plan");
    } finally {
      setLoading(false);
    }
  }

  function toggleSection(index: number) {
    setOpenSections((prev) => ({ ...prev, [index]: !prev[index] }));
  }

  // Debounced 600ms — an undebounced full-replace PUT per keystroke, combined with a since-fixed backend race, used to produce duplicated sections with partial "Unassigned" substrings.
  function persistSections(list: RciSectionItem[]) {
    if (!recordId) return;
    if (persistTimerRef.current) window.clearTimeout(persistTimerRef.current);
    persistTimerRef.current = window.setTimeout(() => {
      updateRciPlanSections(recordId, list)
        .then(() => setPersistError(null))
        .catch((err) => {
          console.error("Failed to persist RCI plan sections", err);
          setPersistError(
            err instanceof ApiError
              ? String(err.detail)
              : "Your last change wasn't saved — check your connection and try the edit again."
          );
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
    const newSection: RciSectionItem = { title: "", correlation: null, assignee: null, due_date: defaultDueDateIso(), tasks: [] };
    const newSections = [...sections, newSection];
    setSections(newSections);
    persistSections(newSections);
    // Open immediately so the new section's blank inputs are visible to fill in right away.
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
    // First-ever assignee pick on this plan bulk-fills every other still-unassigned section as a convenience default; never fires again once any section has a real assignee.
    const isFirstAssignee = !!assignee && sections.every((s) => !s.assignee);
    const newSections = sections.map((s, i) =>
      i === index ? { ...s, assignee } : isFirstAssignee ? { ...s, assignee } : s
    );
    setSections(newSections);
    persistSections(newSections);
  }

  function setSectionDueDate(index: number, dueDate: string) {
    if (!sections) return;
    // Same convenience-default bulk-fill as setSectionAssignee, but for due_date.
    const isFirstDueDate = !!dueDate && sections.every((s) => !s.due_date);
    const newSections = sections.map((s, i) =>
      i === index ? { ...s, due_date: dueDate || null } : isFirstDueDate ? { ...s, due_date: dueDate } : s
    );
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

  function handleExploreEvents() {
    setExploreEventsError(null);
    // Opened synchronously on the click, before the async handoff call — a tab opened after an awaited fetch resolves gets popup-blocked by most browsers.
    const newTab = window.open("", "_blank");
    getEventExplorerHandoffUrl()
      .then(({ url }) => {
        if (newTab) newTab.location.href = url;
      })
      .catch((err) => {
        newTab?.close();
        setExploreEventsError(err instanceof ApiError ? String(err.detail) : "Could not open Event Explorer.");
      });
  }

  // Backend fills the company's RCI Plan Word template (assets/rci_plan_template.docx) with this investigation's persisted sections and returns the file directly.
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

  // Every included section needs an investigator and a TCD before pushing to Trackwise; excluded sections don't need either since they're left out of the final plan.
  const missingAssignments = (sections ?? []).some((s) => (s.is_checked ?? true) && (!s.assignee || !s.due_date));

  async function handleAcceptAndPush() {
    if (missingAssignments) return;
    setShowConfirm(false);
    setExportError(null);
    try {
      await downloadRciPlanDocument();
      setPushed(true);
      setTimeout(() => navigate(`/records/${recordId}/data-interpretation`), 1500);
    } catch (err) {
      setExportError(err instanceof ApiError ? String(err.detail) : "Failed to export the RCI plan document");
    }
  }

  if (!sections) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="card">
          <div className="card-header">
            <p className="card-title">Problem Statement</p>
            {/* Event Explorer button removed from the UI while keeping the handler/state intact. */}
            {false && (
              <button type="button" onClick={handleExploreEvents} className="btn-outline">
                Explore Events
              </button>
            )}
          </div>
          <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12 }}>
            <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-md)", lineHeight: 1.9 }}>{problemStatement}</p>
          </div>
          {exploreEventsError && <p style={{ margin: 0, color: "var(--color-danger-text)" }}>{exploreEventsError}</p>}
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
        <div className="card-header">
          <p className="card-title">Problem Statement</p>
          {/* Event Explorer button removed from the UI while keeping the handler/state intact. */}
          {false && (
            <button type="button" onClick={handleExploreEvents} className="btn-outline">
              Explore Events
            </button>
          )}
        </div>
        <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: 12 }}>
          <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-md)", lineHeight: 1.9 }}>{problemStatement}</p>
        </div>
        {exploreEventsError && <p style={{ margin: 0, color: "var(--color-danger-text)" }}>{exploreEventsError}</p>}
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
      {persistError && <p className="error-banner">{persistError}</p>}

      {sections.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "0 16px", fontSize: "var(--font-size-base)", fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: 0.3 }}>
          <span style={{ width: 20, flexShrink: 0 }} />
          <span style={{ flex: 1, minWidth: 0 }}>Task</span>
          {/* Right-aligned to match the content-fit date box beneath it — Investigator stays left-aligned. */}
          <span style={{ width: 200, flexShrink: 0, textAlign: "right" }}>Target Date</span>
          <span style={{ minWidth: 200 }}>Investigator</span>
          <span style={{ width: 24, flexShrink: 0 }} />
        </div>
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
                  onClick={editMode && !lockedForEditing ? () => toggleSectionIncluded(index) : undefined}
                  aria-label={included ? "Exclude section from final plan" : "Include section in final plan"}
                  title={included ? "Exclude from final plan" : "Include in final plan"}
                  style={{ flexShrink: 0, cursor: editMode && !lockedForEditing ? "pointer" : "default" }}
                  disabled={!editMode || lockedForEditing}
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
                        <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>({section.tasks.length} {section.tasks.length === 1 ? "action" : "actions"})</span>
                      </div>
                      {section.correlation && (
                        <p style={{ margin: "2px 0 0", fontSize: "var(--font-size-base)", color: "var(--color-text-faint)" }}>{section.correlation}</p>
                      )}
                    </>
                  )}
                </div>
                {/* Outer slot keeps the 200px width so the content-fit date box doesn't shift the rest of the row; the box is right-aligned within it. */}
                <div style={{ width: 200, flexShrink: 0, display: "flex", justifyContent: "flex-end", boxSizing: "border-box" }}>
                  <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: "9px 13px", display: "flex", alignItems: "center", gap: 6, fontSize: "var(--font-size-md)", color: "var(--color-text-faint)", width: "fit-content", boxSizing: "border-box" }}>
                    {editMode && !lockedForEditing ? (
                      <input
                        type="date"
                        min={minDueDate}
                        value={section.due_date ?? ""}
                        onChange={(e) => setSectionDueDate(index, e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        style={{ border: "none", background: "none", fontSize: "var(--font-size-md)", color: "var(--color-text-faint)", padding: 0 }}
                      />
                    ) : (
                      <span>{section.due_date ? formatDdMmYyyy(section.due_date) : "—"}</span>
                    )}
                  </div>
                </div>
                <div style={{ background: "var(--color-bg)", border: "1px solid var(--color-card-border)", borderRadius: 4, padding: editMode && !lockedForEditing ? "5px 7px" : "9px 13px", display: "flex", alignItems: "center", gap: 8, minWidth: 200, boxSizing: "border-box" }}>
                  {editMode && !lockedForEditing ? (
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
                  ) : (
                    <span style={{ fontSize: "var(--font-size-md)", color: "var(--color-text-faint)" }}>{section.assignee || "Unassigned"}</span>
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
                    <span style={{ width: "100%" }}>Details</span>
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
                            onClick={editMode && !lockedForEditing ? () => toggleTask(index, taskIndex) : undefined}
                            aria-label={checked ? "Uncheck task" : "Check task"}
                            style={{ flexShrink: 0, marginTop: 2, cursor: editMode && !lockedForEditing ? "pointer" : "default" }}
                            disabled={!editMode || lockedForEditing}
                          >
                            {checked && <img src={checkIcon} alt="" width={12} height={12} />}
                          </button>
                          {editMode && !lockedForEditing ? (
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
                          ) : (
                            <span style={{ fontSize: "var(--font-size-base)", fontWeight: 600, color: "var(--color-text-muted)", flex: 1, minWidth: 0, whiteSpace: "pre-wrap", overflowWrap: "break-word" }}>
                              {task.description}
                            </span>
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
          {pushed ? "Pushed — downloading…" : "Accept and Next"}
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
