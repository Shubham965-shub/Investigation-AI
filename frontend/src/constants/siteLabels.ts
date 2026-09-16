// Display-only: dim_location's "Oral Dosage Form" shows as "KRSG" in filter dropdowns; the real value is still sent to the backend.
const SITE_FILTER_LABEL_OVERRIDES: Record<string, string> = {
  "Oral Dosage Form": "KRSG",
};

export function formatSiteLabel(site: string): string {
  return SITE_FILTER_LABEL_OVERRIDES[site] ?? site;
}