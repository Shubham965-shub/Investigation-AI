// Display-only relabeling for Sites filter dropdowns — per the user
// (2026-07-31, extended to Analytics 2026-08-03), dim_location's real value
// "Oral Dosage Form" should show as "KRSG" in any site filter, without
// changing the underlying value sent to the backend (site filtering still
// matches against the real DB text) or anything else that reads it (e.g. a
// table's own site column, if it's ever shown there). Shared by
// ActionCenterPage and AnalyticsPage.
const SITE_FILTER_LABEL_OVERRIDES: Record<string, string> = {
  "Oral Dosage Form": "KRSG",
};

export function formatSiteLabel(site: string): string {
  return SITE_FILTER_LABEL_OVERRIDES[site] ?? site;
}