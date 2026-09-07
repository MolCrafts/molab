import { describe, expect, it } from "@rstest/core";
import { parseRunsTab, RUNS_TABS, runsTabPath } from "@/app/runs/RunsTabBar";

describe("Runs tabs", () => {
  it("defaults to the inventory list and keeps analytics out of the primary surface", () => {
    // Compare lives here rather than as its own destination: the runs it
    // compares are staged from this table, in the panel docked in the left column.
    expect(RUNS_TABS).toEqual(["jobs", "compare"]);
    expect(parseRunsTab(null)).toBe("jobs");
    expect(parseRunsTab("overview")).toBe("jobs");
    // The Gantt timeline was removed; its URL falls back to the inventory.
    expect(parseRunsTab("timeline")).toBe("jobs");
    expect(parseRunsTab("compare")).toBe("compare");
  });
});

describe("runsTabPath", () => {
  it("round-trips through parseRunsTab", () => {
    for (const tab of RUNS_TABS) {
      const path = runsTabPath(tab);
      const query = path.includes("?") ? new URLSearchParams(path.split("?")[1]) : null;
      expect(parseRunsTab(query?.get("tab") ?? null)).toBe(tab);
    }
  });

  it("spells the default tab by its absence, as writeRunsParams does", () => {
    // A `?tab=jobs` link and a bare `/runs` would be two URLs for one view.
    expect(runsTabPath("jobs")).toBe("/runs");
    expect(runsTabPath("compare")).toBe("/runs?tab=compare");
  });
});
