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
}

export function getRciPlanRecord(recordId: string): Promise<RciPlanRecordResponse | null> {
  return getRecordOrNull<RciPlanRecordResponse>(`/rci-plan/${recordId}`);
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
}

export function getActionCenterSummary(filters?: ActionCenterFilters): Promise<ActionCenterSummaryResponse> {
  const params = new URLSearchParams();
  if (filters?.site) params.set("site", filters.site);
  if (filters?.department) params.set("department", filters.department);
  if (filters?.product) params.set("product", filters.product);
  if (filters?.investigator) params.set("investigator", filters.investigator);
  if (filters?.startDateFrom) params.set("start_date_from", filters.startDateFrom);
  if (filters?.startDateTo) params.set("start_date_to", filters.startDateTo);
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
