import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "@rstest/core";

const here = dirname(fileURLToPath(import.meta.url));
const readRunsSource = (path: string): string => readFileSync(resolve(here, path), "utf8");

describe("Runs performance boundaries", () => {
  it("keeps timeline and inspector code out of the default list chunk", () => {
    const page = readRunsSource("RunsPage.tsx");
    expect(page).toContain('lazy(() =>\n  import("./RunsTimelineView")');
    expect(page).toContain('lazy(() =>\n  import("./inspector/RunInspector")');
    expect(page).toContain('tab === "timeline"');
  });

  it("does not rebuild the complete Gantt config on a wall-clock interval", () => {
    const chart = readRunsSource("RunsGanttChart.tsx");
    expect(chart).not.toContain("setInterval");
    expect(chart).not.toContain("LIVE_TICK_MS");
    expect(chart).toContain("[rows, mode]");
  });
});
