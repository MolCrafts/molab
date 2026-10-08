import { describe, expect, it } from "@rstest/core";
import {
  bypassCacheFor,
  canAnalyzeFailure,
  canHarvest,
  canReproduce,
  canRerun,
  canResume,
  canStart,
  defaultExecutionMode,
  executionModeOptions,
} from "@/app/runs/runLifecycle";

function enabledOf(attempts: number, basedOnStatus: string | null): boolean[] {
  return executionModeOptions({ attempts, basedOnStatus }).map((option) => option.enabled);
}

describe("executionModeOptions", () => {
  it("03a before e01 enables only initial", () => {
    const options = executionModeOptions({ attempts: 0, basedOnStatus: null });
    expect(options.map((option) => option.value)).toEqual([
      "initial",
      "rerun",
      "resume",
      "reproduce",
    ]);
    expect(enabledOf(0, null)).toEqual([true, false, false, false]);
    expect(options[1]?.reason ?? "").toContain("no attempt");
    expect(options.some((option) => option.value === ("retry" as never))).toBe(false);
  });

  it("03a step 2 allows rerun and resume after a failure", () => {
    expect(enabledOf(1, "failed")).toEqual([false, true, true, false]);
  });

  it("03a step 3 refuses resume after success", () => {
    const options = executionModeOptions({ attempts: 2, basedOnStatus: "succeeded" });
    expect(options.map((option) => option.enabled)).toEqual([false, true, false, true]);
    expect(options[2]?.reason ?? "").toContain("succeeded");
  });

  it("03a step 7 refuses rerun while queued", () => {
    const options = executionModeOptions({ attempts: 5, basedOnStatus: "queued" });
    expect(options.map((option) => option.enabled)).toEqual([false, false, false, false]);
    expect(options[1]?.reason ?? "").toContain("cancel");
  });

  it("allows rerun and resume after cancelled, interrupted, or FAILED", () => {
    for (const status of ["cancelled", "interrupted", "FAILED"]) {
      expect(enabledOf(2, status)).toEqual([false, true, true, false]);
    }
  });

  it("refuses every mode while the predecessor is running", () => {
    expect(enabledOf(1, "running")).toEqual([false, false, false, false]);
  });

  it("treats finalizing as still active", () => {
    const options = executionModeOptions({ attempts: 1, basedOnStatus: "finalizing" });
    expect(options.map((option) => option.enabled)).toEqual([false, false, false, false]);
    expect(options[1]?.reason ?? "").toContain("cancel");
  });
});

describe("defaultExecutionMode", () => {
  it("picks initial, then rerun, then rerun when nothing is enabled", () => {
    expect(defaultExecutionMode(executionModeOptions({ attempts: 0, basedOnStatus: null }))).toBe(
      "initial",
    );
    expect(defaultExecutionMode(executionModeOptions({ attempts: 1, basedOnStatus: "failed" }))).toBe(
      "rerun",
    );
    expect(defaultExecutionMode(executionModeOptions({ attempts: 5, basedOnStatus: "queued" }))).toBe(
      "rerun",
    );
  });
});

describe("bypassCacheFor", () => {
  it("forces reproduce and otherwise keeps the request", () => {
    expect(bypassCacheFor("reproduce", false)).toBe(true);
    expect(bypassCacheFor("rerun", true)).toBe(true);
    expect(bypassCacheFor("rerun", false)).toBe(false);
    expect(bypassCacheFor("initial", false)).toBe(false);
  });
});

describe("predecessor predicates", () => {
  it("matches the resumable and terminal sets", () => {
    expect(canResume("interrupted")).toBe(true);
    expect(canResume("succeeded")).toBe(false);
    expect(canRerun("succeeded")).toBe(true);
    expect(canRerun("running")).toBe(false);
    expect(canReproduce("succeeded")).toBe(true);
    expect(canReproduce("failed")).toBe(false);
  });
});

describe("runLifecycle knowledge affordances", () => {
  it("exposes harvest on terminal statuses", () => {
    expect(canHarvest("succeeded")).toBe(true);
    expect(canHarvest("failed")).toBe(true);
    expect(canHarvest("running")).toBe(false);
  });

  it("exposes analyze-failure only on failed", () => {
    expect(canAnalyzeFailure("failed")).toBe(true);
    expect(canAnalyzeFailure("cancelled")).toBe(false);
    expect(canAnalyzeFailure("succeeded")).toBe(false);
  });

  it("keeps start pending-only", () => {
    expect(canStart("pending")).toBe(true);
    expect(canStart("failed")).toBe(false);
  });
});
