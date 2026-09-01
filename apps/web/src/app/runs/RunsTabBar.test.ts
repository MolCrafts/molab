import { describe, expect, it } from "@rstest/core";
import { parseRunsTab, RUNS_TABS } from "@/app/runs/RunsTabBar";

describe("Runs tabs", () => {
  it("defaults to the inventory list and keeps analytics out of the primary surface", () => {
    expect(RUNS_TABS).toEqual(["jobs", "timeline"]);
    expect(parseRunsTab(null)).toBe("jobs");
    expect(parseRunsTab("overview")).toBe("jobs");
    expect(parseRunsTab("timeline")).toBe("timeline");
  });
});
