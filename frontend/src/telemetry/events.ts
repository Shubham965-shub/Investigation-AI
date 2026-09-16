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
  // module workflow
  problemStatementGenerated: "problem_statement_generated",
  problemStatementEdited: "problem_statement_edited",
  rciPlanPushed: "rci_plan_pushed",
  taskCritiqueUploaded: "task_critique_uploaded",
  rcCapaCritiqueUploaded: "rc_capa_critique_uploaded",
  rciReportGenerated: "rci_report_generated",
} as const;

export type EventName = (typeof EVENTS)[keyof typeof EVENTS];
