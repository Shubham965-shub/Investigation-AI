import { ApiError, apiGet, apiGetBlob, apiPost, apiPostForm, apiPut } from "./client";
import type { EventType, TrackwiseFields } from "../constants/trackwiseFields";
import { toRciSegment } from "../lib/rci";

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

// 404 means "no record yet" (expected — page shows a blank form), so resolve to null instead of throwing; any other failure still throws (see DbErrorModal).
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
  rciId: string | null,
  request: TrackwiseRequest
): Promise<ProblemStatementResponse> {
  return apiPost<ProblemStatementResponse>(`/problem-statement/${recordId}/${toRciSegment(rciId)}/generate`, request);
}

// One concrete, real difference between the raw TrackWise text and the generated problem statement.
export interface ProblemStatementEnhancement {
  category: string;
  tw_excerpt: string;
  llm_excerpt: string;
}

export interface ProblemStatementRecordResponse {
  record_id: string;
  event_type: EventType;
  trackwise_fields: TrackwiseFields;
  problem_statement: string | null;
  // True once Evidence Collection has data — Problem Statement becomes read-only (see ProblemStatementPage.tsx's lockedForEditing).
  locked_for_editing?: boolean;
  // Verbatim dim_event.criticality; only meaningful for Deviation/Market Complaint — drives which SLA tier the Stepper applies.
  criticality?: string | null;
  // dim_event.event_classification — additive, not a replacement for criticality (which stays binary Critical/Non-Critical); "Critical"|"Major"|"Minor" or null. Shown as a tag on the Record Details header.
  event_classification?: string | null;
  // null = never generated yet ("Generate" affordance); [] = generated, nothing meaningful found; cleared server-side whenever the problem statement is manually edited.
  enhancements?: ProblemStatementEnhancement[] | null;
}

export function getProblemStatementRecord(
  recordId: string,
  rciId: string | null
): Promise<ProblemStatementRecordResponse | null> {
  return getRecordOrNull<ProblemStatementRecordResponse>(`/problem-statement/${recordId}/${toRciSegment(rciId)}`);
}

// Persists a manual edit to the generated problem statement — previously session-only, lost on refresh/navigation.
export function updateProblemStatement(
  recordId: string,
  rciId: string | null,
  problemStatement: string
): Promise<ProblemStatementRecordResponse> {
  return apiPut<ProblemStatementRecordResponse>(`/problem-statement/${recordId}/${toRciSegment(rciId)}`, { problem_statement: problemStatement });
}

export interface ProblemStatementEnhancementsResponse {
  enhancements: ProblemStatementEnhancement[];
}

// Reads both the raw TrackWise description and the already-generated problem statement
// server-side — no body needed. Persisted, so this is a one-time LLM call per generation/edit.
export function generateProblemStatementEnhancements(
  recordId: string,
  rciId: string | null
): Promise<ProblemStatementEnhancementsResponse> {
  return apiPost<ProblemStatementEnhancementsResponse>(`/problem-statement/${recordId}/${toRciSegment(rciId)}/enhancements/generate`, {});
}

export interface SimilarInvestigation {
  deviation_id: number;
  title: string;
  status: "Open" | "Closed" | "Cancelled" | "Unknown";
  relevance_score: number;
}

export function getSimilarInvestigations(recordId: string, rciId: string | null): Promise<SimilarInvestigation[]> {
  return apiGet<SimilarInvestigation[]>(`/problem-statement/${recordId}/${toRciSegment(rciId)}/historic`);
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
  rciId: string | null,
  request: TrackwiseRequest
): Promise<EvidenceCollectionResponse> {
  return apiPost<EvidenceCollectionResponse>(`/evidence/${recordId}/${toRciSegment(rciId)}/collect`, request);
}

export interface EvidenceCollectionRecordResponse {
  record_id: string;
  event_type: EventType;
  trackwise_fields: TrackwiseFields;
  evidence: EvidenceItem[] | null;
}

export function getEvidenceRecord(
  recordId: string,
  rciId: string | null
): Promise<EvidenceCollectionRecordResponse | null> {
  return getRecordOrNull<EvidenceCollectionRecordResponse>(`/evidence/${recordId}/${toRciSegment(rciId)}`);
}

// Full replace of check/uncheck state + user-added items, same persistence pattern as generation.
export function updateEvidenceItems(recordId: string, rciId: string | null, items: EvidenceItem[]): Promise<void> {
  return apiPut<void>(`/evidence/${recordId}/${toRciSegment(rciId)}`, items);
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
  rciId: string | null,
  request: TrackwiseRequest
): Promise<QuestionnaireResponse> {
  return apiPost<QuestionnaireResponse>(`/questionnaire/${recordId}/${toRciSegment(rciId)}/generate`, request);
}

export interface QuestionnaireRecordResponse {
  record_id: string;
  event_type: EventType;
  trackwise_fields: TrackwiseFields;
  questions: InterviewQuestion[] | null;
}

export function getQuestionnaireRecord(
  recordId: string,
  rciId: string | null
): Promise<QuestionnaireRecordResponse | null> {
  return getRecordOrNull<QuestionnaireRecordResponse>(`/questionnaire/${recordId}/${toRciSegment(rciId)}`);
}

// Full replace of check/uncheck state + user-added questions, same persistence pattern as generation.
export function updateQuestionnaireItems(recordId: string, rciId: string | null, items: InterviewQuestion[]): Promise<void> {
  return apiPut<void>(`/questionnaire/${recordId}/${toRciSegment(rciId)}`, items);
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
  // Whole-section include/exclude from the final plan — same convention as RciTaskItem.is_checked, one level up.
  is_checked?: boolean;
  // investigation_rci_sections.id — only populated on read-back; used by Task Critique to attach history to a section.
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
  rciId: string | null,
  request: TrackwiseRequest
): Promise<RciPlanResponse> {
  return apiPost<RciPlanResponse>(`/rci-plan/${recordId}/${toRciSegment(rciId)}/generate`, request);
}

export interface RciPlanRecordResponse {
  record_id: string;
  event_type: EventType;
  trackwise_fields: TrackwiseFields;
  sections: RciSectionItem[] | null;
  // True once Task Critique has started on any section — RCI Plan becomes read-only (see RciPlanPage.tsx's lockedForEditing).
  locked_for_editing?: boolean;
}

export function getRciPlanRecord(recordId: string, rciId: string | null): Promise<RciPlanRecordResponse | null> {
  return getRecordOrNull<RciPlanRecordResponse>(`/rci-plan/${recordId}/${toRciSegment(rciId)}`);
}

// Investigators on OPEN investigations only, for the per-section dropdown. Registered ahead of GET /rci-plan/{record_id} on the backend so this literal path isn't shadowed by that catch-all.
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

// Full replace of section fields (investigator edits etc.), same pattern as evidence/questionnaire persistence.
export function updateRciPlanSections(recordId: string, rciId: string | null, sections: RciSectionItem[]): Promise<void> {
  return apiPut<void>(`/rci-plan/${recordId}/${toRciSegment(rciId)}`, sections);
}

// Filled from the company's RCI Plan Word template (backend/assets/rci_plan_template.docx).
export function exportRciPlanDocx(recordId: string, rciId: string | null): Promise<Blob> {
  return apiGetBlob(`/rci-plan/${recordId}/${toRciSegment(rciId)}/export`);
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

// One row of ds's /score/report `info` breakdown (mirrors ds's InfoRow); shown via an info icon next to each score. Shared by Task Critique and RC & CAPA.
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
  // DS-generated; task_score stays null until DS returns one (or permanently, for an is_gospel report).
  summary: string | null;
  task_score: number | null;
  score_breakdown: ScoreBreakdownTable[];
  // True when ds's critique came back degenerate (no tasks found) — only possible for reports uploaded before pre-upload checks existed.
  critique_failed: boolean;
  uploaded_at: string;
  recommendations: TaskCritiqueRecommendation[];
}

export interface TaskCritiqueSection {
  // 0-based position within the RCI Plan document's extracted task list — not a DB row id.
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
  // False when neither the RCI Plan export nor a manually-uploaded stand-in document exists yet.
  has_source_document: boolean;
  source_document_name: string | null;
}

export function getTaskCritique(recordId: string, rciId: string | null): Promise<TaskCritiqueListResponse | null> {
  return getRecordOrNull<TaskCritiqueListResponse>(`/task-critique/${recordId}/${toRciSegment(rciId)}`);
}

export function uploadTaskCritiqueSourceDocument(recordId: string, rciId: string | null, file: File): Promise<TaskCritiqueListResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<TaskCritiqueListResponse>(`/task-critique/${recordId}/${toRciSegment(rciId)}/source-document`, formData);
}

export function uploadTaskCritiqueReport(recordId: string, rciId: string | null, taskIndex: number, file: File): Promise<TaskCritiqueSection> {
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<TaskCritiqueSection>(`/task-critique/${recordId}/${toRciSegment(rciId)}/sections/${taskIndex}/upload`, formData);
}

export function decideTaskCritiqueRecommendation(
  recordId: string,
  rciId: string | null,
  taskIndex: number,
  recommendationId: number,
  decision: "accepted" | "rejected",
  reason?: string
): Promise<TaskCritiqueSection> {
  return apiPost<TaskCritiqueSection>(
    `/task-critique/${recordId}/${toRciSegment(rciId)}/sections/${taskIndex}/recommendations/${recommendationId}/decision`,
    { decision, reason }
  );
}

// Full audit trail across every attempt for one task; stays available even once the task is scored and done.
export interface RecommendationHistoryAttempt {
  attempt_number: number;
  summary: string | null;
  recommendations: TaskCritiqueRecommendation[];
  created_at: string;
}

export function getTaskCritiqueHistory(recordId: string, rciId: string | null, taskIndex: number): Promise<RecommendationHistoryAttempt[]> {
  return apiGet<RecommendationHistoryAttempt[]>(`/task-critique/${recordId}/${toRciSegment(rciId)}/sections/${taskIndex}/history`);
}

// ── RC & CAPA Critique ────────────────────────────────────────────────────

export interface RcCapaRecommendation {
  id: number;
  description: string;
  // Only set for rc_impact recommendations — "rc" vs "impact", rendered as two subsections; null for capa recommendations (and older rc_impact rows).
  type: "rc" | "impact" | null;
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
  impact_score: number | null;
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

export function getRcCapaCritique(recordId: string, rciId: string | null): Promise<RcCapaState | null> {
  return getRecordOrNull<RcCapaState>(`/rc-capa-critique/${recordId}/${toRciSegment(rciId)}`);
}

export function uploadRcCapaCritiqueReport(recordId: string, rciId: string | null, file: File): Promise<RcCapaState> {
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<RcCapaState>(`/rc-capa-critique/${recordId}/${toRciSegment(rciId)}/upload`, formData);
}

export function decideRcCapaRecommendation(
  recordId: string,
  rciId: string | null,
  recommendationId: number,
  decision: "accepted" | "rejected",
  reason?: string
): Promise<RcCapaState> {
  return apiPost<RcCapaState>(`/rc-capa-critique/${recordId}/${toRciSegment(rciId)}/recommendations/${recommendationId}/decision`, { decision, reason });
}

// Every report, oldest first — investigation_rc_capa_reports keeps a real row per attempt (never upserted), unlike Task Critique.
export function getRcCapaHistory(recordId: string, rciId: string | null): Promise<RcCapaReport[]> {
  return apiGet<RcCapaReport[]>(`/rc-capa-critique/${recordId}/${toRciSegment(rciId)}/history`);
}

export function pushRcCapaToSitReview(recordId: string, rciId: string | null): Promise<RcCapaState> {
  return apiPost<RcCapaState>(`/rc-capa-critique/${recordId}/${toRciSegment(rciId)}/push-to-sit-review`, {});
}

// ── Action Center ─────────────────────────────────────────────────────────

export interface MonthlyBar {
  label: string;
  count: number;
}

export interface MonthlyTrend {
  monthly: MonthlyBar[];
  trend_percent: number | null;
}

export interface EventTypeCount {
  label: string;
  count: number;
  percent: number;
  closed_trend: MonthlyTrend;
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
  // TrackWise's own status-derived stage — the original progress signal, now the secondary
  // toggled-on column (see investigator_stage below for the default one).
  stage: number;
  // Default progress bar: the module stage of the last item generated/uploaded by a user holding
  // the Investigator role specifically. Can move backward if an Investigator regenerates an
  // earlier module after reaching a later one — literal "most recent", not a ratchet.
  investigator_stage: number;
  total_stages: number;
  bucket: "unassigned" | "on_track" | "delay" | "overdue";
  site: string | null;
  department: string | null;
  product: string | null;
  is_cancelled: boolean;
  rci_ids: string[];
  escalation_level: string | null;
  oos_oot_phase: "Phase 1" | "Phase 2" | null;
  criticality: string | null;
  // dim_event.event_classification — additive, not a replacement for criticality (binary Critical/Non-Critical); "Critical"|"Major"|"Minor" or null. Drives the flag shown in front of the event-type badge.
  event_classification: string | null;
  // SIT Dashboard's "Remark" column, keyed by rci_id ("" for none) — a deviation with multiple RCI IDs renders as multiple rows, each with its own remark. Populated only for the SIT role.
  remarks: Record<string, string>;
  // `investigator` above is just whichever fact_qms_event row the backend's dedup picked — wrong for multi-RCI investigations, where each rci_key can have a different investigator. Keyed by rci_id; fall back to `investigator` if absent.
  investigator_by_rci: Record<string, string | null>;
  // Per-rci_id module stage, mirroring investigator_by_rci's convention — lets each multi-RCI sub-row show its own progress instead of reusing the parent's single scalar investigator_stage.
  investigator_stage_by_rci: Record<string, number>;
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
  opened_trend: MonthlyTrend;
  status_cards: StatusCardResponse[];
  // Same 4 cards as status_cards, scoped per event type — keyed by event_type_counts[].label.
  status_cards_by_event_type: Record<string, StatusCardResponse[]>;
  pending_actions: PendingActionResponse[];
  chart: ChartBarResponse[];
  investigations: InvestigationRowResponse[];
  filter_options: FilterOptions;
  // "Last updated" stamp shown top-right of the page — raw fact_qms_event.pg_updated_at_timestamp; null only if the table is empty.
  last_updated_at: string | null;
}

export interface ActionCenterFilters {
  site?: string;
  department?: string;
  product?: string;
  investigator?: string;
  startDateFrom?: string;
  startDateTo?: string;
  // "cancelled" shows only cancelled investigations instead of the default open-only list; stat cards/chart/pending actions are always open-only regardless.
  status?: "open" | "cancelled";
  // Page-wide filter, unlike `status` above — narrows stat cards/chart/pending actions AND the investigations table.
  criticality?: "critical" | "non_critical";
  // OOS/OOT-only equivalent of `criticality` — those event types show Phase 1/Phase 2 instead of Major/Minor, so it's a separate param rather than overloading criticality's values.
  oosOotPhase?: "phase1" | "phase2";
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
  if (filters?.oosOotPhase) params.set("oos_oot_phase", filters.oosOotPhase);
  const qs = params.toString();
  return apiGet<ActionCenterSummaryResponse>(`/action-center/summary${qs ? `?${qs}` : ""}`);
}

// SIT-only edit; backend enforces this too (403 for anyone else), not just a UI gate. rciId is "" for a row with no RCI ID, matching InvestigationRowResponse.remarks.
export function updateInvestigationRemark(recordId: string, rciId: string, remark: string): Promise<{ remark: string }> {
  return apiPut<{ remark: string }>(`/action-center/${recordId}/remark`, { rci_id: rciId, remark });
}

// ── Analytics ─────────────────────────────────────────────────────────────
// IQ Score and the CAPA L1-L5 ranking have no backing data in the star schema and stay mock in AnalyticsPage.tsx (see backend/routers/analytics.py docstring).

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
  // Same "last updated" stamp as ActionCenterSummaryResponse.
  last_updated_at: string | null;
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

// ── RCI Report ──────────────────────────────────────────────────────────
// Field names/types mirror backend/backend/schemas/rci_report.py 1:1 (which itself mirrors ds's schemas).

export interface SourcedTextItem {
  value: string;
  source: "trackwise" | "manual_entry_required" | "manual_entry_provided" | "synthesized";
}

// Each field is a list of bullet-point strings, not one prose string (readability) — mirrors backend/ds ExecutiveSummarySection exactly.
export interface ExecutiveSummarySection {
  summary: string[];
  problem_description: string[];
  immediate_containment_action: string[];
  determination_of_root_cause: string[];
  root_cause_probable_cause_statement: string[];
  impact_assessment: string[];
  correction_conclusion_preventive_actions: string[];
  conclusion_statement: string[];
}

export interface DescriptionOfEventSection {
  what_happened: string;
  when_happened: string;
  who_identified: string;
  where_it_happened: string;
  nonconforming_reference: SourcedTextItem;
  how_detected: SourcedTextItem;
}

export type ImpactType = "Direct" | "Indirect" | "Not applicable";

export interface MaterialProductImpactItem {
  material_product_batch: string;
  batch_number: string;
  quantity_involved: string;
  quantity_on_hold: SourcedTextItem;
  type_of_impact: ImpactType;
}

export interface EquipmentActionChecklist {
  operation_suspended: boolean;
  on_hold_label_affixed: boolean;
  other_action_taken: boolean;
  other_action_specify: string;
}

export interface EquipmentImpactItem {
  equipment_instrument: SourcedTextItem;
  identification_number: SourcedTextItem;
  actions_initiated: EquipmentActionChecklist;
}

export interface InitialImpactAssessmentSection {
  material_product_impacts: MaterialProductImpactItem[];
  equipment_impacts: EquipmentImpactItem[];
  immediate_actions: string[];
}

export interface HistoryReviewRow {
  event_number: string;
  event_title: string;
  capa_description: string;
  capa_implementation_date: string;
}

export interface HistoryReviewSection {
  lookback_months: number;
  search_scope_note: string;
  rows: HistoryReviewRow[];
  no_similar_events_found: boolean;
  closing_narrative: string;
  batches_manufactured_note?: string | null;
}

export type SixMFactor = "Man" | "Machine" | "Material" | "Method" | "Measurement" | "Mother Nature";

export const SIX_M_FACTOR_OPTIONS: SixMFactor[] = ["Man", "Machine", "Material", "Method", "Measurement", "Mother Nature"];

export interface TaskSummaryItem {
  tick: string;
  title: string;
  six_m_factor: SixMFactor;
  outcome: string;
}

export interface InvestigationTaskSummarySection {
  overview: string;
  tasks: TaskSummaryItem[];
}

export interface RootCauseTaskLink {
  tick: string;
  title: string;
  six_m_factor: SixMFactor;
  explanation: string;
}

export interface RootCauseIdentificationSection {
  grounding_evidence: string;
  applicable_tasks: RootCauseTaskLink[];
}

export interface WhyWhyStep {
  question: string;
  answer: string;
}

export interface WhyWhyAnalysisSection {
  six_m_factor: SixMFactor;
  method_rationale: string;
  why_why_chain: WhyWhyStep[];
}

export interface InvestigationTaskSection {
  task_summary: InvestigationTaskSummarySection;
  why_why_analysis: WhyWhyAnalysisSection;
  root_cause_identification: RootCauseIdentificationSection;
}

export interface RootCauseTaxonomy {
  category: SixMFactor;
  sub_category: string;
}

export interface RootCauseConclusionSection {
  conclusion: string;
  taxonomy: RootCauseTaxonomy;
  repeat_occurrence_evidence: string;
  is_repeat_occurrence: boolean;
}

export interface ImpactSubsectionItem {
  applicable: boolean;
  narrative: string;
}

export interface BatchShipperImpact {
  batch_number: string;
  number_of_shippers: string;
  defects: string;
}

export interface ImpactOnAffectedBatchSubsection extends ImpactSubsectionItem {
  batch_shipper_table: BatchShipperImpact[];
}

export interface ImpactAssessmentBatchDispositionSection {
  impact_on_affected_batches: ImpactOnAffectedBatchSubsection;
  impact_on_marketed_released_batches: ImpactSubsectionItem;
  impact_on_other_product_material_area_process: ImpactSubsectionItem;
  impact_on_regulatory_filing: ImpactSubsectionItem;
  impact_on_facility_equipment_instrument: ImpactSubsectionItem;
  impact_on_manufacturing_process_analytical_method: ImpactSubsectionItem;
  business_continuity: ImpactSubsectionItem;
  impact_on_data_integrity: ImpactSubsectionItem;
  stability_repackaging_requirement: ImpactSubsectionItem;
  patient_safety: ImpactSubsectionItem;
  others_as_applicable: ImpactSubsectionItem;
  conclusion: string;
  medical_investigation_summary?: string | null;
  health_hazard_evaluation?: string | null;
  impact_justification?: string | null;
}

// Plain (non-table) ImpactSubsection fields, in display order — impact_on_affected_batches is handled separately (it has the extra batch_shipper_table).
export const IMPACT_SUBSECTION_FIELDS: { key: keyof ImpactAssessmentBatchDispositionSection; label: string }[] = [
  { key: "impact_on_marketed_released_batches", label: "Impact on Marketed / Released Batches" },
  { key: "impact_on_other_product_material_area_process", label: "Impact on Other Product / Material / Area / Process" },
  { key: "impact_on_regulatory_filing", label: "Impact on Regulatory Filing" },
  { key: "impact_on_facility_equipment_instrument", label: "Impact on Facility / Equipment / Instrument" },
  { key: "impact_on_manufacturing_process_analytical_method", label: "Impact on Manufacturing Process / Analytical Method" },
  { key: "business_continuity", label: "Business Continuity" },
  { key: "impact_on_data_integrity", label: "Impact on Data Integrity" },
  { key: "stability_repackaging_requirement", label: "Stability / Repackaging Requirement" },
  { key: "patient_safety", label: "Patient Safety" },
  { key: "others_as_applicable", label: "Others, as Applicable" },
];

export type SeverityTier = "Critical" | "Medium" | "Low";
export type RepeatabilityTier = "High" | "Medium" | "Low";
export type DetectabilityTier = "High" | "Medium" | "Low";
export type RiskLevel = "L1" | "L2" | "L3" | "L4" | "L5";

export interface TierSelection<T extends string> {
  grounding_evidence: string;
  tier: T;
}

export interface RiskFactorScores {
  severity: TierSelection<SeverityTier>;
  repeatability: TierSelection<RepeatabilityTier>;
  detectability: TierSelection<DetectabilityTier>;
}

export interface RiskAssessmentCandidate {
  cause_label: string;
  factors: RiskFactorScores;
  severity_score: number;
  repeatability_score: number;
  detectability_score: number;
  rpn: number;
  risk_level: RiskLevel;
}

export interface RiskAssessmentSection {
  applicability_reason: string;
  applicable: "yes" | "no — unconfirmed market complaint";
  candidates: RiskAssessmentCandidate[];
}

export interface ObservationStatusItem {
  observation: string;
  status: string;
  reference_number?: string | null;
}

export interface CorrectionRemedialActionSection {
  items: ObservationStatusItem[];
  additional_notes: string[];
}

export interface CAPAActionItem {
  description: string;
  responsibility?: string | null;
  due_date: string;
}

export interface InterimControlItem {
  description: string;
  responsibility: string;
  due_date: string;
}

export interface CAPAExtrapolationItem {
  applicable: boolean;
  justification: string;
  scope_description: string;
  related_customers: string[];
  related_markets: string[];
  capa_numbers: string[];
  related_change_controls: string[];
  responsibility: string;
  due_date: string;
}

export interface CAPASection {
  capa_not_applicable_justification?: string | null;
  capa_actions: CAPAActionItem[];
  interim_controls: InterimControlItem[];
  extrapolation: CAPAExtrapolationItem;
}

export type DurationTier = "short" | "standard" | "extended";
export type CAPAMechanism = "Procedural / training-based" | "Resource / equipment substitution" | "Other";
export const DURATION_TIER_OPTIONS: DurationTier[] = ["short", "standard", "extended"];
export const CAPA_MECHANISM_OPTIONS: CAPAMechanism[] = ["Procedural / training-based", "Resource / equipment substitution", "Other"];

export interface CAPAEffectivenessPlanItem {
  grounding_evidence: string;
  capa_mechanism: CAPAMechanism;
  capa_description: string;
  effectiveness_check: string[];
  effectiveness_criteria: string[];
  responsibility: string;
  duration_rationale: string;
  duration_tier: DurationTier;
  monitoring_duration: string;
}

export interface CAPAEffectivenessCheckPlanSection {
  capa_not_applicable_justification?: string | null;
  generated_plans: CAPAEffectivenessPlanItem[];
}

export interface AnnexureItem {
  annexure_no: string;
  title: string;
}

export interface ApprovalRow {
  role: string;
  name?: string | null;
  title?: string | null;
  department?: string | null;
  signature_date?: string | null;
}

export interface AnnexuresSection {
  items: AnnexureItem[];
}

export interface ApprovalSection {
  rows: ApprovalRow[];
}

export interface RciReportSections {
  event_type: string;
  // Every section is nullable — ds skips one rather than failing the whole request when a required field is blank; `errors` explains why, keyed by field name.
  executive_summary: ExecutiveSummarySection | null;
  description_of_event: DescriptionOfEventSection | null;
  initial_impact_assessment: InitialImpactAssessmentSection | null;
  history_review: HistoryReviewSection | null;
  investigation_task: InvestigationTaskSection | null;
  root_cause_conclusion: RootCauseConclusionSection | null;
  impact_assessment_batch_disposition: ImpactAssessmentBatchDispositionSection | null;
  risk_assessment: RiskAssessmentSection | null;
  correction_remedial_action: CorrectionRemedialActionSection | null;
  capa: CAPASection | null;
  capa_effectiveness_check_plan: CAPAEffectivenessCheckPlanSection | null;
  annexures: AnnexuresSection;
  approval: ApprovalSection;
  errors: Record<string, string>;
}

export interface RciReportRecordResponse {
  record_id: string;
  event_type: EventType;
  trackwise_fields: TrackwiseFields;
  report: RciReportSections | null;
  generated_at: string | null;
  mc_confirmed: boolean | null;
  manual_entries: Record<string, string>;
}

export function getRciReportRecord(recordId: string, rciId: string | null): Promise<RciReportRecordResponse | null> {
  return getRecordOrNull<RciReportRecordResponse>(`/rci-report/${recordId}/${toRciSegment(rciId)}`);
}

export function updateRciReportInputs(
  recordId: string,
  rciId: string | null,
  mcConfirmed: boolean | null,
  manualEntries: Record<string, string>
): Promise<RciReportRecordResponse> {
  return apiPut<RciReportRecordResponse>(`/rci-report/${recordId}/${toRciSegment(rciId)}/inputs`, { mc_confirmed: mcConfirmed, manual_entries: manualEntries });
}

export function generateRciReport(recordId: string, rciId: string | null): Promise<RciReportRecordResponse> {
  return apiPost<RciReportRecordResponse>(`/rci-report/${recordId}/${toRciSegment(rciId)}/generate`, {});
}

export function updateRciReportSections(recordId: string, rciId: string | null, report: RciReportSections): Promise<RciReportRecordResponse> {
  return apiPut<RciReportRecordResponse>(`/rci-report/${recordId}/${toRciSegment(rciId)}`, report);
}

// The real .docx for "Download and View" — filled from the company's RCI Report Word template with the persisted report.
export function exportRciReportDocx(recordId: string, rciId: string | null): Promise<Blob> {
  return apiGetBlob(`/rci-report/${recordId}/${toRciSegment(rciId)}/export`);
}
