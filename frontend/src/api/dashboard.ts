import { ApiError, apiGet, apiGetBlob, apiPost, apiPostForm, apiPut } from "./client";
import type { EventType, TrackwiseFields } from "../constants/trackwiseFields";

export interface ArchetypeInfo {
  id: number | null;
  name: string;
  is_new: boolean;
  confidence_score: number | null;
  reasoning: string | null;
}

interface TrackwiseRequest {
  event_type: EventType;
  trackwise_fields: TrackwiseFields;
}

/** GET /{module}/{recordId}: 404 means "no real DB record for this id yet" —
 * an expected, non-error outcome (the page shows its blank entry form), so it
 * resolves to null instead of throwing. Any other failure still throws, and
 * callers surface it as a blocking error (see DbErrorModal). */
async function getRecordOrNull<T>(path: string): Promise<T | null> {
  try {
    return await apiGet<T>(path);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

// ── Problem statement generation ─────────────────────────────────────────

export interface ProblemStatementResponse {
  event_type: string;
  problem_statement: string;
}

export function generateProblemStatement(
  recordId: string,
  request: TrackwiseRequest
): Promise<ProblemStatementResponse> {
  return apiPost<ProblemStatementResponse>(`/problem-statement/${recordId}/generate`, request);
}

export interface ProblemStatementRecordResponse {
  record_id: string;
  event_type: EventType;
  trackwise_fields: TrackwiseFields;
  problem_statement: string | null;
  // True once Evidence Collection has any real data — Problem Statement is
  // read-only at that point (see ProblemStatementPage.tsx's lockedForEditing).
  locked_for_editing?: boolean;
}

export function getProblemStatementRecord(
  recordId: string
): Promise<ProblemStatementRecordResponse | null> {
  return getRecordOrNull<ProblemStatementRecordResponse>(`/problem-statement/${recordId}`);
}

export interface SimilarInvestigation {
  deviation_id: number;
  title: string;
  status: "Open" | "Closed" | "Cancelled" | "Unknown";
  relevance_score: number;
}

export function getSimilarInvestigations(recordId: string): Promise<SimilarInvestigation[]> {
  return apiGet<SimilarInvestigation[]>(`/problem-statement/${recordId}/historic`);
}

// ── Evidence collection ──────────────────────────────────────────────────

export interface EvidenceItem {
  description: string;
  is_new: boolean;
  is_checked?: boolean;
}

export interface EvidenceCollectionResponse {
  event_type: string;
  failure_type: string;
  archetype: ArchetypeInfo;
  evidence: EvidenceItem[];
  total_evidence_count: number;
}

export function collectEvidence(
  recordId: string,
  request: TrackwiseRequest
): Promise<EvidenceCollectionResponse> {
  return apiPost<EvidenceCollectionResponse>(`/evidence/${recordId}/collect`, request);
}

export interface EvidenceCollectionRecordResponse {
  record_id: string;
  event_type: EventType;
  trackwise_fields: TrackwiseFields;
  evidence: EvidenceItem[] | null;
}

export function getEvidenceRecord(
  recordId: string
): Promise<EvidenceCollectionRecordResponse | null> {
  return getRecordOrNull<EvidenceCollectionRecordResponse>(`/evidence/${recordId}`);
}

/** Persists the current check/uncheck state + any user-added items — full
 * replace, same as generation's own persistence, just triggered by edits. */
export function updateEvidenceItems(recordId: string, items: EvidenceItem[]): Promise<void> {
  return apiPut<void>(`/evidence/${recordId}`, items);
}

// ── Interview questionnaire ───────────────────────────────────────────────

export interface InterviewQuestion {
  description: string;
  is_new: boolean;
  is_checked?: boolean;
}

export interface QuestionnaireResponse {
  event_type: string;
  failure_type: string;
  archetype: ArchetypeInfo;
  questions: InterviewQuestion[];
  total_questions_count: number;
}

export function generateQuestionnaire(
  recordId: string,
  request: TrackwiseRequest
): Promise<QuestionnaireResponse> {
  return apiPost<QuestionnaireResponse>(`/questionnaire/${recordId}/generate`, request);
}

export interface QuestionnaireRecordResponse {
  record_id: string;
  event_type: EventType;
  trackwise_fields: TrackwiseFields;
  questions: InterviewQuestion[] | null;
}

export function getQuestionnaireRecord(
  recordId: string
): Promise<QuestionnaireRecordResponse | null> {
  return getRecordOrNull<QuestionnaireRecordResponse>(`/questionnaire/${recordId}`);
}

/** Persists the current check/uncheck state + any user-added questions —
 * full replace, same as generation's own persistence, just triggered by edits. */
export function updateQuestionnaireItems(recordId: string, items: InterviewQuestion[]): Promise<void> {
  return apiPut<void>(`/questionnaire/${recordId}`, items);
}

// ── RCI plan ──────────────────────────────────────────────────────────────

export interface RciTaskItem {
  description: string;
  is_checked?: boolean;
}

export interface RciSectionItem {
  title: string;
  correlation: string | null;
  tasks: RciTaskItem[];
  due_date?: string | null;
  assignee?: string | null;
  // Whole-section include/exclude from the final plan (2026-08-20, per the
  // user) — same convention as RciTaskItem.is_checked, one level up.
  is_checked?: boolean;
  // investigation_rci_sections.id — only populated on read-back, used by
  // Task Critique to attach report/recommendation history to a section.
  id?: number | null;
}

export interface RciPlanResponse {
  event_type: string;
  failure_type: string;
  archetype: ArchetypeInfo;
  sections: RciSectionItem[];
  total_sections_count: number;
  total_tasks_count: number;
}

export function generateRciPlan(
  recordId: string,
  request: TrackwiseRequest
): Promise<RciPlanResponse> {
  return apiPost<RciPlanResponse>(`/rci-plan/${recordId}/generate`, request);
}

export interface RciPlanRecordResponse {
  record_id: string;
  event_type: EventType;
  trackwise_fields: TrackwiseFields;
  sections: RciSectionItem[] | null;
  // True once Task Critique has started on any section — RCI Plan is
  // read-only at that point (see RciPlanPage.tsx's lockedForEditing).
  locked_for_editing?: boolean;
}

export function getRciPlanRecord(recordId: string): Promise<RciPlanRecordResponse | null> {
  return getRecordOrNull<RciPlanRecordResponse>(`/rci-plan/${recordId}`);
}

/** Investigators currently assigned to an OPEN investigation only
 * (2026-08-19, per the user, re-scoping the prior 2026-08-13 all-time list)
 * — populates the per-section Investigator dropdown. Registered ahead of
 * GET /rci-plan/{record_id} on the backend so this literal path isn't
 * shadowed by that catch-all. */
export function getOpenInvestigators(): Promise<string[]> {
  return apiGet<string[]>("/rci-plan/investigators");
}

export interface RciTemplateUploadResponse {
  status: string;
  message: string;
  archetypes_processed: string[];
  plans_created: number;
  sections_created: number;
  tasks_created: number;
}

/** Persists investigator-name edits (and any other section field changes) —
 * full replace, same pattern as evidence/questionnaire persistence. */
export function updateRciPlanSections(recordId: string, sections: RciSectionItem[]): Promise<void> {
  return apiPut<void>(`/rci-plan/${recordId}`, sections);
}

/** The real .docx file — filled from the company's RCI Plan Word template
 * (backend/assets/rci_plan_template.docx) with this investigation's data. */
export function exportRciPlanDocx(recordId: string): Promise<Blob> {
  return apiGetBlob(`/rci-plan/${recordId}/export`);
}

export function uploadRciTemplates(file: File): Promise<RciTemplateUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<RciTemplateUploadResponse>("/rci-plan/upload", formData);
}

// ── Task Critique ─────────────────────────────────────────────────────────

export interface TaskCritiqueRecommendation {
  id: number;
  description: string;
  decision: "pending" | "accepted" | "rejected";
  reason: string | null;
}

// One row / one section table of ds's /score/report `info` breakdown —
// mirrors ds's InfoRow/InfoTable (2026-08-14, per the user: shown via a small
// info icon next to each generated score). Shared shape for both Task
// Critique and RC & CAPA Critique.
export interface ScoreBreakdownRow {
  id: string;
  checkpoint: string;
  max: number;
  verdict: string;
  score: number;
  rationale: string;
  evidence_quote: string;
}

export interface ScoreBreakdownTable {
  section: string; // task_report | rc | impact | capa
  label: string;
  native_max: number;
  marks_awarded: number;
  percentage: number;
  rows: ScoreBreakdownRow[];
}

export interface TaskCritiqueReport {
  id: number;
  attempt_number: number;
  file_name: string;
  is_gospel: boolean;
  // DS-generated (/critique/analyse-task-report) — task_score stays null
  // until DS returns one (or permanently, for an is_gospel report).
  summary: string | null;
  task_score: number | null;
  score_breakdown: ScoreBreakdownTable[];
  // True when ds's critique came back degenerate (no real tasks found to
  // review) — only ever true for reports uploaded before the pre-upload
  // format/degenerate-result checks existed.
  critique_failed: boolean;
  uploaded_at: string;
  recommendations: TaskCritiqueRecommendation[];
}

export interface TaskCritiqueSection {
  // 0-based position within the RCI Plan document's extracted task list —
  // not a DB row id.
  task_index: number;
  title: string;
  correlation: string | null;
  task_count: number;
  due_date: string | null;
  assignee: string | null;
  status: "pending" | "in_progress" | "complete";
  upload_count: number;
  max_uploads: number;
  locked: boolean;
  next_upload_is_final: boolean;
  can_upload: boolean;
  latest_report: TaskCritiqueReport | null;
}

export interface TaskCritiqueListResponse {
  record_id: string;
  sections: TaskCritiqueSection[];
  // False when neither module 4's RCI Plan export nor a manually-uploaded
  // stand-in document exists yet.
  has_source_document: boolean;
  source_document_name: string | null;
}

export function getTaskCritique(recordId: string): Promise<TaskCritiqueListResponse | null> {
  return getRecordOrNull<TaskCritiqueListResponse>(`/task-critique/${recordId}`);
}

export function uploadTaskCritiqueSourceDocument(recordId: string, file: File): Promise<TaskCritiqueListResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<TaskCritiqueListResponse>(`/task-critique/${recordId}/source-document`, formData);
}

export function uploadTaskCritiqueReport(recordId: string, taskIndex: number, file: File): Promise<TaskCritiqueSection> {
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<TaskCritiqueSection>(`/task-critique/${recordId}/sections/${taskIndex}/upload`, formData);
}

export function decideTaskCritiqueRecommendation(
  recordId: string,
  taskIndex: number,
  recommendationId: number,
  decision: "accepted" | "rejected",
  reason?: string
): Promise<TaskCritiqueSection> {
  return apiPost<TaskCritiqueSection>(
    `/task-critique/${recordId}/sections/${taskIndex}/recommendations/${recommendationId}/decision`,
    { decision, reason }
  );
}

// The full audit trail across every attempt for one task — independent of
// lock/complete state, so it stays available even once the task is scored
// and done (2026-08-18, per the user). Same rich decision-tracking shape as
// the live report's recommendations, kept in sync as decisions are made.
export interface RecommendationHistoryAttempt {
  attempt_number: number;
  summary: string | null;
  recommendations: TaskCritiqueRecommendation[];
  created_at: string;
}

export function getTaskCritiqueHistory(recordId: string, taskIndex: number): Promise<RecommendationHistoryAttempt[]> {
  return apiGet<RecommendationHistoryAttempt[]>(`/task-critique/${recordId}/sections/${taskIndex}/history`);
}

// ── RC & CAPA Critique ────────────────────────────────────────────────────

export interface RcCapaRecommendation {
  id: number;
  description: string;
  decision: "pending" | "accepted" | "rejected";
  reason: string | null;
}

export interface RcCapaCritique {
  category: "rc_impact" | "capa";
  summary: string | null;
  recommendations: RcCapaRecommendation[];
}

export interface RcCapaReport {
  id: number;
  attempt_number: number;
  file_name: string;
  is_gospel: boolean;
  rc_score: number | null;
  capa_score: number | null;
  total_score: number | null;
  score_breakdown: ScoreBreakdownTable[];
  uploaded_at: string;
  critiques: RcCapaCritique[];
}

export interface RcCapaState {
  record_id: string;
  status: "pending" | "in_progress" | "complete";
  upload_count: number;
  max_uploads: number;
  locked: boolean;
  next_upload_is_final: boolean;
  can_upload: boolean;
  latest_report: RcCapaReport | null;
  sit_review_status: "pending" | null;
  investigator: string | null;
  due_date: string | null;
}

export function getRcCapaCritique(recordId: string): Promise<RcCapaState | null> {
  return getRecordOrNull<RcCapaState>(`/rc-capa-critique/${recordId}`);
}

export function uploadRcCapaCritiqueReport(recordId: string, file: File): Promise<RcCapaState> {
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<RcCapaState>(`/rc-capa-critique/${recordId}/upload`, formData);
}

export function decideRcCapaRecommendation(
  recordId: string,
  recommendationId: number,
  decision: "accepted" | "rejected",
  reason?: string
): Promise<RcCapaState> {
  return apiPost<RcCapaState>(`/rc-capa-critique/${recordId}/recommendations/${recommendationId}/decision`, { decision, reason });
}

// The full audit trail across every attempt — unlike Task Critique,
// investigation_rc_capa_reports already keeps a real row per attempt
// (never upserted in place), so this is just every report, oldest first.
// Independent of lock/complete state (2026-08-18, per the user) — surfaced
// behind its own button/panel rather than inline.
export function getRcCapaHistory(recordId: string): Promise<RcCapaReport[]> {
  return apiGet<RcCapaReport[]>(`/rc-capa-critique/${recordId}/history`);
}

export function pushRcCapaToSitReview(recordId: string): Promise<RcCapaState> {
  return apiPost<RcCapaState>(`/rc-capa-critique/${recordId}/push-to-sit-review`, {});
}

// ── Action Center ─────────────────────────────────────────────────────────

export interface EventTypeCount {
  label: string;
  count: number;
  percent: number;
}

export interface StatusCardResponse {
  key: string;
  label: string;
  count: number;
  rows: [string, number][];
}

export interface PendingActionResponse {
  id: string;
  title: string;
  due_date: string | null;
  is_overdue: boolean;
  is_unassigned: boolean;
  criticality: string | null;
  action: string;
  // Drives the panel's fixed two-row layout: row 1 = OOS, row 2 = Deviation.
  event_type: string;
}

export interface InvestigationRowResponse {
  id: string;
  title: string;
  event_type: string;
  investigator: string | null;
  start_date: string | null;
  due_date: string | null;
  updated_at: string | null;
  stage: number;
  total_stages: number;
  bucket: "unassigned" | "on_track" | "delay" | "overdue";
  site: string | null;
  department: string | null;
  product: string | null;
  is_cancelled: boolean;
}

export interface FilterOptions {
  sites: string[];
  departments: string[];
  products: string[];
  investigators: string[];
}

export interface ChartBarResponse {
  label: string;
  on_track: number;
  at_risk: number;
  delayed: number;
}

export interface ActionCenterSummaryResponse {
  total_investigations: number;
  event_type_counts: EventTypeCount[];
  status_cards: StatusCardResponse[];
  // Same 4 cards as status_cards, scoped to just that event type — keyed by
  // the same labels as event_type_counts[].label.
  status_cards_by_event_type: Record<string, StatusCardResponse[]>;
  pending_actions: PendingActionResponse[];
  chart: ChartBarResponse[];
  investigations: InvestigationRowResponse[];
  filter_options: FilterOptions;
}

export interface ActionCenterFilters {
  site?: string;
  department?: string;
  product?: string;
  investigator?: string;
  startDateFrom?: string;
  startDateTo?: string;
  // "cancelled" shows only cancelled investigations instead of the default
  // open-only list (2026-08-13, per the user) — stat cards/chart/pending
  // actions are unaffected either way, they've always been open-only.
  status?: "open" | "cancelled";
  // Page-wide filter (2026-08-14, per the user) — unlike `status` above, this
  // narrows stat cards/chart/pending actions AND the investigations table.
  criticality?: "critical" | "non_critical";
}

export function getActionCenterSummary(filters?: ActionCenterFilters): Promise<ActionCenterSummaryResponse> {
  const params = new URLSearchParams();
  if (filters?.site) params.set("site", filters.site);
  if (filters?.department) params.set("department", filters.department);
  if (filters?.product) params.set("product", filters.product);
  if (filters?.investigator) params.set("investigator", filters.investigator);
  if (filters?.startDateFrom) params.set("start_date_from", filters.startDateFrom);
  if (filters?.startDateTo) params.set("start_date_to", filters.startDateTo);
  if (filters?.status) params.set("status", filters.status);
  if (filters?.criticality) params.set("criticality", filters.criticality);
  const qs = params.toString();
  return apiGet<ActionCenterSummaryResponse>(`/action-center/summary${qs ? `?${qs}` : ""}`);
}

// ── Analytics ─────────────────────────────────────────────────────────────
// Only the data-groundable sections are real (see backend/routers/analytics.py
// module docstring) — Investigation Quality (IQ Score) and the CAPA L1-L5
// hierarchy ranking have no backing data anywhere in the star schema and stay
// mock in AnalyticsPage.tsx until a real formula/mapping is defined.

export interface EventTypeCardResponse {
  key: string;
  label: string;
  total: number;
  in_progress: number;
  closed: number;
  overdue: number;
  overdue_pct: number;
  trend_pct: number | null;
}

export interface RootCauseStatusResponse {
  identified: number;
  not_identified: number;
  total: number;
}

export interface CategoryCountResponse {
  label: string;
  count: number;
}

export interface MonthCountResponse {
  label: string;
  value: number;
}

export interface CapaStatusResponse {
  with_capa: number;
  without_capa: number;
  total: number;
  monthly_trend: MonthCountResponse[];
  by_root_cause_category: CategoryCountResponse[];
}

export interface FrequencyRowResponse {
  label: string;
  value: number;
}

export interface FailurePatternsResponse {
  products: FrequencyRowResponse[];
  equipment: FrequencyRowResponse[];
}

export interface AnalyticsFilterOptions {
  sites: string[];
  departments: string[];
  products: string[];
  equipment: string[];
}

export interface AnalyticsSummaryResponse {
  events: EventTypeCardResponse[];
  root_cause_status: RootCauseStatusResponse;
  root_cause_categories: CategoryCountResponse[];
  capa: CapaStatusResponse;
  failure_patterns: FailurePatternsResponse;
  filter_options: AnalyticsFilterOptions;
}

export interface AnalyticsFilters {
  site?: string;
  department?: string;
  product?: string;
  equipment?: string;
  startDateFrom?: string;
}

export function getAnalyticsSummary(filters?: AnalyticsFilters): Promise<AnalyticsSummaryResponse> {
  const params = new URLSearchParams();
  if (filters?.site) params.set("site", filters.site);
  if (filters?.department) params.set("department", filters.department);
  if (filters?.product) params.set("product", filters.product);
  if (filters?.equipment) params.set("equipment", filters.equipment);
  if (filters?.startDateFrom) params.set("start_date_from", filters.startDateFrom);
  const qs = params.toString();
  return apiGet<AnalyticsSummaryResponse>(`/analytics/summary${qs ? `?${qs}` : ""}`);
}
