import { describe, expect, it } from "vitest";
import { RCI_NONE, toRciSegment, fromRciSegment, recordPath } from "./rci";

describe("toRciSegment", () => {
  it("returns the literal 'none' sentinel for null/undefined/empty", () => {
    expect(toRciSegment(null)).toBe(RCI_NONE);
    expect(toRciSegment(undefined)).toBe(RCI_NONE);
    expect(toRciSegment("")).toBe(RCI_NONE);
  });

  it("passes a real rci_id through unchanged", () => {
    expect(toRciSegment("504544")).toBe("504544");
  });
});

describe("fromRciSegment", () => {
  it("maps the 'none' sentinel (and undefined) back to empty string", () => {
    expect(fromRciSegment(RCI_NONE)).toBe("");
    expect(fromRciSegment(undefined)).toBe("");
  });

  it("passes a real rci_id segment through unchanged", () => {
    expect(fromRciSegment("504544")).toBe("504544");
  });

  it("round-trips through toRciSegment for both the none case and a real id", () => {
    expect(fromRciSegment(toRciSegment(null))).toBe("");
    expect(fromRciSegment(toRciSegment("504544"))).toBe("504544");
  });
});

describe("recordPath", () => {
  it("builds a path with the 'none' sentinel when there's no rci_id", () => {
    expect(recordPath("503935", null, "problem-statement")).toBe("/records/503935/none/problem-statement");
  });

  it("builds a path with the real rci_id when one is given", () => {
    expect(recordPath("503935", "504544", "rci-plan")).toBe("/records/503935/504544/rci-plan");
  });
});
