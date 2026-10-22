import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "@rstest/core";

const here = dirname(fileURLToPath(import.meta.url));
const readRunsSource = (path: string): string => readFileSync(resolve(here, path), "utf8");

describe("Runs performance boundaries", () => {
  it("keeps inspector code out of the default list chunk", () => {
    const page = readRunsSource("RunsPage.tsx");
    expect(page).toContain('lazy(() =>\n  import("./inspector/RunInspector")');
  });

  // The Gantt timeline was a second, worse answer to "what ran when" that the
  // jobs table already gives — it is gone, chart and tab alike.
  it("has no timeline surface left to lazy-load", () => {
    const page = readRunsSource("RunsPage.tsx");
    expect(page).not.toContain("RunsTimelineView");
    expect(page).not.toContain("Gantt");
  });
});
