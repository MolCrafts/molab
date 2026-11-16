import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "@rstest/core";

const here = dirname(fileURLToPath(import.meta.url));
const readRunsSource = (path: string): string => readFileSync(resolve(here, path), "utf8");

describe("Runs performance boundaries", () => {
  it("keeps run detail out of the list: a row hands the run to the shell's Preview", () => {
    const page = readRunsSource("RunsPage.tsx");
    // L12: the Runs page names a target; the Preview module renders it.
    expect(page).toContain("usePreview");
    expect(page).not.toContain("RunInspector");
    expect(page).not.toContain("RunPreview");
  });

  // The Gantt timeline was a second, worse answer to "what ran when" that the
  // jobs table already gives — it is gone, chart and tab alike.
  it("has no timeline surface left to lazy-load", () => {
    const page = readRunsSource("RunsPage.tsx");
    expect(page).not.toContain("RunsTimelineView");
    expect(page).not.toContain("Gantt");
  });
});
