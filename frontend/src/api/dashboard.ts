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
  // Verbatim dim_event.criticality (upstream/Trackwise) — only meaningful
  // for Deviation/Market Complaint (2026-08-26, per the user: used by
  // Stepper to pick which SLA tier applies to this investigation).
  criticality?: string | null;
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
  // Only set for rc_impact category recommendations — "rc" (evidence/
  // traceability/history) vs "impact" (impact linkage), rendered as two
  // separate subsections. null for capa recommendations, and for any
  // rc_impact recommendation saved before this field existed.
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
  escalation_level: string | null;
  oos_oot_phase: "Phase 1" | "Phase 2" | null;
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
  // OOS/OOT-only equivalent of `criticality` above (2026-08-25, per the
  // user) — those two event types show Phase 1/Phase 2 instead of Major &
  // Minor in the same toggle, so this is a separate param rather than
  // overloading criticality's values. Same page-wide scope as criticality.
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

// ── RCI Report ──────────────────────────────────────────────────────────
// Field names/types mirror backend/backend/schemas/rci_report.py 1:1, which
// itself mirrors ds's own schemas verbatim — see that file's docstring.

export interface SourcedTextItem {
  value: string;
  source: "trackwise" | "manual_entry_required" | "manual_entry_provided" | "synthesized";
}

export interface ExecutiveSummarySection {
  summary: string;
  problem_description: string;
  immediate_containment_action: string;
  determination_of_root_cause: string;
  root_cause_probable_cause_statement: string;
  impact_assessment: string;
  correction_conclusion_preventive_actions: string;
  conclusion_statement: string;
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
  stage: string;
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

// Methods ds can actually demonstrate step-by-step (RCAToolDemonstration.method)
// — a narrower set than the RCA methods an investigation might merely name;
// GEMBA Walk/FMEA/"Not explicitly stated" have no structured demonstration
// shape below, so they're not offered here (matches backend's
// RCADemonstrableMethod literal exactly, schemas/rci_report.py).
export type RCADemonstrableMethod = "Why-Why Analysis" | "Fishbone / Ishikawa" | "Fault Tree Analysis" | "Flowchart / Process Mapping";
export type SixMFactor = "Man" | "Machine" | "Material" | "Method" | "Measurement" | "Mother Nature";

export const RCA_DEMONSTRABLE_METHOD_OPTIONS: RCADemonstrableMethod[] = [
  "Why-Why Analysis",
  "Fishbone / Ishikawa",
  "Fault Tree Analysis",
  "Flowchart / Process Mapping",
];
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

export interface FishboneBranch {
  six_m_factor: SixMFactor;
  causes: string[];
}

export interface FaultTreeNode {
  event: string;
  contributing_causes: string[];
}

export interface FlowchartStep {
  step_number: number;
  description: string;
  decision_point?: string | null;
}

export interface RCAToolDemonstration {
  method: RCADemonstrableMethod;
  method_rationale: string;
  why_why_chain: WhyWhyStep[];
  fishbone_branches: FishboneBranch[];
  fault_tree: FaultTreeNode[];
  flowchart_steps: FlowchartStep[];
}

export interface InvestigationTaskSection {
  task_summary: InvestigationTaskSummarySection;
  root_cause_identification: RootCauseIdentificationSection;
  rca_tool_demonstrations: RCAToolDemonstration[];
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

// Plain (non-table) ImpactSubsection fields on ImpactAssessmentBatchDispositionSection,
// in display order — impact_on_affected_batches is handled separately (it has the
// extra batch_shipper_table).
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
  // Every section is nullable — ds skips one rather than failing the whole
  // request when a required TrackWise field is blank, or when a section it
  // depends on was itself skipped. `errors` explains why, keyed by field name.
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

export function getRciReportRecord(recordId: string): Promise<RciReportRecordResponse | null> {
  return getRecordOrNull<RciReportRecordResponse>(`/rci-report/${recordId}`);
}

export function updateRciReportInputs(
  recordId: string,
  mcConfirmed: boolean | null,
  manualEntries: Record<string, string>
): Promise<RciReportRecordResponse> {
  return apiPut<RciReportRecordResponse>(`/rci-report/${recordId}/inputs`, { mc_confirmed: mcConfirmed, manual_entries: manualEntries });
}

export function generateRciReport(recordId: string): Promise<RciReportRecordResponse> {
  return apiPost<RciReportRecordResponse>(`/rci-report/${recordId}/generate`, {});
}

export function updateRciReportSections(recordId: string, report: RciReportSections): Promise<RciReportRecordResponse> {
  return apiPut<RciReportRecordResponse>(`/rci-report/${recordId}`, report);
}

/** The real .docx download for "Download and View" — filled from the
 * company's RCI Report Word template with this investigation's persisted
 * report (2026-08-25, per the user). */
export function exportRciReportDocx(recordId: string): Promise<Blob> {
  return apiGetBlob(`/rci-report/${recordId}/export`);
}
