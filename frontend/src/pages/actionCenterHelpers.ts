// Pure, stateless helpers extracted out of ActionCenterPage.tsx so they're testable without
// pulling in that page's full dependency graph (API calls, auth context, telemetry, icons, CSS).
import type { InvestigationRowResponse } from "../api/dashboard";

// Unassigned and L5-L1 are independent dimensions, not a partition — an investigation can be both Unassigned and L1, so this uses `bucket` rather than deriving "unassigned" from a missing escalation_level.
export function matchesStatusCard(inv: InvestigationRowResponse, cardKey: string): boolean {
  // Phase 1/Phase 2 are standalone cards, independent of assignment status — only present when scoped to OOS/OOT.
  if (cardKey === "phase1") return inv.oos_oot_phase === "Phase 1";
  if (cardKey === "phase2") return inv.oos_oot_phase === "Phase 2";
  if (cardKey === "unassigned") return inv.bucket === "unassigned";
  return inv.escalation_level === cardKey;
}

// Real backend bucket -> the table/grid status-pill styling + label.
export const BUCKET_TO_STATUS: Record<string, { status: string; label: string }> = {
  unassigned: { status: "unassigned", label: "Unassigned" },
  delay: { status: "due-soon", label: "At Risk of Delay" },
  on_track: { status: "in-progress", label: "In Progress" },
  overdue: { status: "overdue", label: "Overdue" },
};

// Must match the backend's _UNASSIGNED_INVESTIGATOR_FILTER sentinel exactly.
export const UNASSIGNED_INVESTIGATOR_FILTER = "__unassigned__";

export function formatInvestigatorLabel(investigator: string): string {
  return investigator === UNASSIGNED_INVESTIGATOR_FILTER ? "Unassigned" : investigator;
}

// Every column except "Investigation" itself is sortable.
export type SortColumn = "product" | "investigator" | "progress" | "start_date" | "due_date" | "status";

// Dates are pre-formatted strings ("29 Jul 2026"), not ISO — parse to a timestamp so sort is chronological, not alphabetical by month name.
export function parseDisplayDateMs(value: string | null): number | null {
  if (!value) return null;
  const ms = new Date(value).getTime();
  return Number.isNaN(ms) ? null : ms;
}

export function getSortValue(inv: InvestigationRowResponse, column: SortColumn): string | number | null {
  switch (column) {
    case "product":
      return inv.product;
    case "investigator":
      return inv.investigator;
    case "progress":
      return inv.total_stages ? inv.investigator_stage / inv.total_stages : 0;
    case "start_date":
      return parseDisplayDateMs(inv.start_date);
    case "due_date":
      return parseDisplayDateMs(inv.due_date);
    case "status":
      return inv.is_cancelled ? "Cancelled" : (BUCKET_TO_STATUS[inv.bucket] ?? BUCKET_TO_STATUS.unassigned).label;
  }
}

// Nulls always sort to the end regardless of direction — flipping them on "desc" would put blanks first.
export function compareForSort(a: string | number | null, b: string | number | null, direction: "asc" | "desc"): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  const cmp = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));
  return direction === "asc" ? cmp : -cmp;
}

// Grey (neutral) when trend is 0/undefined — previous month's count was 0, so a % change isn't meaningful.
export function trendTone(trendPercent: number | null): "neutral" | "warm" | "cool" {
  if (!trendPercent) return "neutral";
  return trendPercent < 0 ? "warm" : "cool";
}

// Static per event type, independent of the MoM trend coloring above.
export function eventTypeAccentClass(label: string): "event-deviation" | "event-oos" | "event-oot" | "event-mc" {
  if (label === "OOS") return "event-oos";
  if (label === "OOT") return "event-oot";
  if (label === "Market Complaint") return "event-mc";
  return "event-deviation";
}

// Only Major/Minor show here, no "Non Critical" tag — null means unclassified or no Major/Minor concept (OOS/OOT), not "non-critical". Critical itself is a separate badge driven by criticality.
export function classificationFlag(inv: InvestigationRowResponse): { label: string; className: string } | null {
  if (inv.event_classification === "Major") return { label: "Major", className: "classification-major" };
  if (inv.event_classification === "Minor") return { label: "Minor", className: "classification-minor" };
  return null;
}

// Rounds max up to a "nice" axis ceiling (1-2-5-10 step sequence) so bars stay proportional to a real 0 baseline, with headroom above the tallest bar.
export function niceAxisMax(max: number, targetSteps = 4): number {
  if (max <= 0) return 1;
  const rawStep = max / targetSteps;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
  return Math.ceil(max / step) * step;
}

// Shows first/last plus a window around the current page, collapsing the rest into an ellipsis for large page counts.
export function pageNumbers(current: number, total: number): (number | "…")[] {
  const pages = new Set<number>([1, total, current, current - 1, current + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
  const result: (number | "…")[] = [];
  sorted.forEach((p, idx) => {
    if (idx > 0 && p - sorted[idx - 1] > 1) result.push("…");
    result.push(p);
  });
  return result;
}
