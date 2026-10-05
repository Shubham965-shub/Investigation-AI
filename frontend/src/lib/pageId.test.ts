import { describe, expect, it } from "vitest";
import { pageIdForPath } from "./pageId";

describe("pageIdForPath", () => {
  it("maps known static routes to their pageview id", () => {
    expect(pageIdForPath("/login")).toBe("login");
    expect(pageIdForPath("/")).toBe("action-center");
    expect(pageIdForPath("/analytics")).toBe("analytics");
    expect(pageIdForPath("/user-management")).toBe("user-management");
    expect(pageIdForPath("/cxo-dashboard")).toBe("cxo-dashboard");
  });

  it("extracts the step from a record route, with or without the 'none' rci sentinel", () => {
    expect(pageIdForPath("/records/503935/504544/problem-statement")).toBe("problem-statement");
    expect(pageIdForPath("/records/503935/none/rci-plan")).toBe("rci-plan");
  });

  it("maps task-critique with a sub-segment to the detail page id, but not without one", () => {
    expect(pageIdForPath("/records/503935/504544/task-critique/0")).toBe("task-critique-detail");
    expect(pageIdForPath("/records/503935/504544/task-critique")).toBe("task-critique");
  });

  it("returns null for anything that doesn't match a known pattern", () => {
    expect(pageIdForPath("/some/random/path")).toBeNull();
    expect(pageIdForPath("/records/503935")).toBeNull();
  });
});
