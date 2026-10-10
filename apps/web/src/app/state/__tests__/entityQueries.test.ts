import { describe, expect, it } from "@rstest/core";
import { artifactPreviewText, journalRefetchInterval, runKeys } from "@/app/state/entityQueries";

describe("runKeys.journal", () => {
  it("keys one execution journal", () => {
    expect(runKeys.journal("p", "e", "r", "e01")).toEqual([
      "runs",
      "p",
      "e",
      "r",
      "e01",
      "journal",
    ]);
  });
});

describe("runKeys.artifactContent", () => {
  it("keys one artifact's bytes", () => {
    expect(runKeys.artifactContent("p", "e", "r", "e01", "a1")).toEqual([
      "runs",
      "p",
      "e",
      "r",
      "e01",
      "artifacts",
      "a1",
      "content",
    ]);
  });
});

describe("journalRefetchInterval", () => {
  it("polls while an attempt is queued or running", () => {
    expect(journalRefetchInterval("running")).toBe(1500);
    expect(journalRefetchInterval("queued")).toBe(1500);
    expect(journalRefetchInterval("finalizing")).toBe(1500);
  });

  it("stops for a terminal or missing status", () => {
    expect(journalRefetchInterval("failed")).toBe(false);
    expect(journalRefetchInterval(undefined)).toBe(false);
  });
});

describe("artifactPreviewText", () => {
  it("passes a string through", () => {
    expect(artifactPreviewText("abc")).toBe("abc");
  });

  it("pretty-prints an object", () => {
    expect(artifactPreviewText({ a: 1 })).toBe('{\n  "a": 1\n}');
  });

  it("turns null into an empty string", () => {
    expect(artifactPreviewText(null)).toBe("");
  });

  it("caps the preview at 300 000 characters", () => {
    expect(artifactPreviewText("x".repeat(300_001))).toHaveLength(300_000);
  });
});
