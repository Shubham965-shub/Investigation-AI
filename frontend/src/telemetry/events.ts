// Central event taxonomy so custom telemetry names stay consistent across the app — import from here, never hardcode a string.
export { track, capturePageview, posthog, posthogEnabled } from "./posthog";

export const EVENTS = {
  // auth
  loginSucceeded: "login_succeeded",
  loginFailed: "login_failed",
  logout: "logout",
  // navigation
  recordStepViewed: "record_step_viewed",
  // Action Center / SIT Dashboard
  filterChanged: "filter_changed",
  statusCardClicked: "status_card_clicked",
  investigationRowExpanded: "investigation_row_expanded",
  remarkSaved: "remark_saved",
  viewModeChanged: "view_mode_changed",
  sortChanged: "sort_changed",
  progressColumnToggled: "progress_column_toggled",
  investigationOpened: "investigation_opened",
  // module workflow
  problemStatementGenerated: "problem_statement_generated",
  problemStatementEdited: "problem_statement_edited",
  moduleStepAdvanced: "module_step_advanced",
  rciPlanGenerated: "rci_plan_generated",
  rciPlanPushed: "rci_plan_pushed",
  eventExplorerOpened: "event_explorer_opened",
  // Task Critique / RC&CAPA Critique uploads are now background-processed (2026-09-28) — the
  // *Uploaded events below fire when the upload request is sent, *UploadResolved fires once the
  // existing poll loop detects the background critique/scoring finished (status prop:
  // "complete" | "critique_failed").
  taskCritiqueUploaded: "task_critique_uploaded",
  taskCritiqueUploadResolved: "task_critique_upload_resolved",
  rcCapaCritiqueUploaded: "rc_capa_critique_uploaded",
  rcCapaCritiqueUploadResolved: "rc_capa_critique_upload_resolved",
  rcCapaPushedToSitReview: "rc_capa_pushed_to_sit_review",
  rciReportGenerated: "rci_report_generated",
  rciReportDownloaded: "rci_report_downloaded",
  // CXO Dashboard
  cxoDomainChanged: "cxo_domain_changed",
  // User Management
  userRoleChanged: "user_role_changed",
  userCreated: "user_created",
  // InvestigationPreviewPanel's 3 click sites all funnel into the same navigation action — one
  // event, `trigger` prop distinguishes which control fired it.
  previewStepOpened: "preview_step_opened",
} as const;

export type EventName = (typeof EVENTS)[keyof typeof EVENTS];
