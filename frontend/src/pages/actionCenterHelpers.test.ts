import { describe, expect, it } from "vitest";
import type { InvestigationRowResponse } from "../api/dashboard";
import {
  matchesStatusCard,
  formatInvestigatorLabel,
  UNASSIGNED_INVESTIGATOR_FILTER,
  parseDisplayDateMs,
  getSortValue,
  compareForSort,
  trendTone,
  eventTypeAccentClass,
  classificationFlag,
  niceAxisMax,
  pageNumbers,
} from "./actionCenterHelpers";

function makeInvestigation(overrides: Partial<InvestigationRowResponse> = {}): InvestigationRowResponse {
  return {
    record_id: "503935",
    rci_id: null,
    product: "Product A",
    investigator: "Jane Doe",
    bucket: "on_track",
    escalation_level: null,
    oos_oot_phase: null,
    total_stages: 4,
    investigator_stage: 2,
    start_date: "01 Jan 2026",
    due_date: "15 Jan 2026",
    is_cancelled: false,
    event_classification: null,
    ...overrides,
  } as InvestigationRowResponse;
}

describe("matchesStatusCard", () => {
  it("matches phase cards off oos_oot_phase, independent of bucket", () => {
    expect(matchesStatusCard(makeInvestigation({ oos_oot_phase: "Phase 1" }), "phase1")).toBe(true);
    expect(matchesStatusCard(makeInvestigation({ oos_oot_phase: "Phase 2" }), "phase1")).toBe(false);
    expect(matchesStatusCard(makeInvestigation({ oos_oot_phase: "Phase 2" }), "phase2")).toBe(true);
  });

  it("matches the unassigned card off bucket, not escalation_level", () => {
    expect(matchesStatusCard(makeInvestigation({ bucket: "unassigned", escalation_level: "L1" }), "unassigned")).toBe(true);
    expect(matchesStatusCard(makeInvestigation({ bucket: "on_track" }), "unassigned")).toBe(false);
  });

  it("falls back to comparing escalation_level directly for L1-L5 cards", () => {
    expect(matchesStatusCard(makeInvestigation({ escalation_level: "L3" }), "L3")).toBe(true);
    expect(matchesStatusCard(makeInvestigation({ escalation_level: "L3" }), "L4")).toBe(false);
  });
});

describe("formatInvestigatorLabel", () => {
  it("maps the unassigned sentinel to a human label", () => {
    expect(formatInvestigatorLabel(UNASSIGNED_INVESTIGATOR_FILTER)).toBe("Unassigned");
  });

  it("passes through any other investigator name unchanged", () => {
    expect(formatInvestigatorLabel("Jane Doe")).toBe("Jane Doe");
  });
});

describe("parseDisplayDateMs", () => {
  it("parses a formatted display date to a timestamp", () => {
    expect(parseDisplayDateMs("01 Jan 2026")).toBe(new Date("01 Jan 2026").getTime());
  });

  it("returns null for null or unparseable input", () => {
    expect(parseDisplayDateMs(null)).toBeNull();
    expect(parseDisplayDateMs("not a date")).toBeNull();
  });
});

describe("getSortValue", () => {
  it("computes progress as a fraction of total_stages", () => {
    expect(getSortValue(makeInvestigation({ total_stages: 4, investigator_stage: 2 }), "progress")).toBe(0.5);
  });

  it("returns 0 progress when total_stages is 0, avoiding a division by zero", () => {
    expect(getSortValue(makeInvestigation({ total_stages: 0, investigator_stage: 0 }), "progress")).toBe(0);
  });

  it("reports 'Cancelled' status regardless of bucket when is_cancelled is true", () => {
    expect(getSortValue(makeInvestigation({ is_cancelled: true, bucket: "on_track" }), "status")).toBe("Cancelled");
  });

  it("otherwise derives status label from bucket", () => {
    expect(getSortValue(makeInvestigation({ bucket: "overdue" }), "status")).toBe("Overdue");
  });
});

describe("compareForSort", () => {
  it("always sorts nulls to the end, regardless of direction", () => {
    expect(compareForSort(null, 5, "asc")).toBe(1);
    expect(compareForSort(5, null, "asc")).toBe(-1);
    expect(compareForSort(null, 5, "desc")).toBe(1);
    expect(compareForSort(5, null, "desc")).toBe(-1);
  });

  it("compares numbers numerically and strings lexicographically", () => {
    expect(compareForSort(1, 2, "asc")).toBeLessThan(0);
    expect(compareForSort("b", "a", "asc")).toBeGreaterThan(0);
  });

  it("flips comparison order for desc", () => {
    expect(compareForSort(1, 2, "desc")).toBeGreaterThan(0);
  });
});

describe("trendTone", () => {
  it("is neutral for null or zero trend", () => {
    expect(trendTone(null)).toBe("neutral");
    expect(trendTone(0)).toBe("neutral");
  });

  it("is warm for negative trend, cool for positive", () => {
    expect(trendTone(-10)).toBe("warm");
    expect(trendTone(10)).toBe("cool");
  });
});

describe("eventTypeAccentClass", () => {
  it("maps known event type labels to their accent class", () => {
    expect(eventTypeAccentClass("OOS")).toBe("event-oos");
    expect(eventTypeAccentClass("OOT")).toBe("event-oot");
    expect(eventTypeAccentClass("Market Complaint")).toBe("event-mc");
  });

  it("defaults to the deviation accent for anything else", () => {
    expect(eventTypeAccentClass("Deviation")).toBe("event-deviation");
  });
});

describe("classificationFlag", () => {
  it("flags Major and Minor classifications", () => {
    expect(classificationFlag(makeInvestigation({ event_classification: "Major" }))).toEqual({ label: "Major", className: "classification-major" });
    expect(classificationFlag(makeInvestigation({ event_classification: "Minor" }))).toEqual({ label: "Minor", className: "classification-minor" });
  });

  it("returns null for anything else, including unclassified", () => {
    expect(classificationFlag(makeInvestigation({ event_classification: null }))).toBeNull();
  });
});

describe("niceAxisMax", () => {
  it("returns 1 for a non-positive max", () => {
    expect(niceAxisMax(0)).toBe(1);
    expect(niceAxisMax(-5)).toBe(1);
  });

  it("rounds up to a nice 1-2-5-10 step ceiling", () => {
    expect(niceAxisMax(9, 4)).toBe(10);
    expect(niceAxisMax(42, 4)).toBe(60);
  });
});

describe("pageNumbers", () => {
  it("shows every page when the total is small", () => {
    expect(pageNumbers(1, 3)).toEqual([1, 2, 3]);
  });

  it("collapses distant pages into an ellipsis around the current page", () => {
    expect(pageNumbers(5, 10)).toEqual([1, "…", 4, 5, 6, "…", 10]);
  });

  it("omits the leading ellipsis when the current page is near the start", () => {
    expect(pageNumbers(1, 10)).toEqual([1, 2, "…", 10]);
  });
});
