/**
 * Round-trip tests for filterParams: URL → WorkspaceRunsFilters → URL.
 */

import { describe, expect, it } from "@rstest/core";

import {
  absorbFacetTokens,
  hasActiveFilters,
  parseFilterParams,
  toggleArrayFilter,
  toggleStarted,
  writeFilterParams,
} from "@/app/runs/filterParams";

describe("parseFilterParams", () => {
  it("decodes comma-separated multi-value params", () => {
    const params = new URLSearchParams("status=running,failed&backend=slurm");
    expect(parseFilterParams(params)).toEqual({
      status: ["running", "failed"],
      backend: ["slurm"],
    });
  });

  it("keeps known Started windows and the free tokens", () => {
    const params = new URLSearchParams("started=24h,bogus&q=driver:ase");
    expect(parseFilterParams(params)).toEqual({ started: ["24h"], q: "driver:ase" });
  });
});

describe("writeFilterParams", () => {
  it("clears keys when their array is empty", () => {
    const prev = new URLSearchParams("status=running&backend=slurm");
    const next = writeFilterParams(prev, { backend: ["slurm"] });
    expect(next.get("status")).toBeNull();
    expect(next.get("backend")).toBe("slurm");
  });

  it("preserves unrelated params", () => {
    const prev = new URLSearchParams("runId=abc");
    const next = writeFilterParams(prev, { status: ["running"] });
    expect(next.get("runId")).toBe("abc");
    expect(next.get("status")).toBe("running");
  });
});

describe("toggleArrayFilter", () => {
  it("adds a value not present", () => {
    const next = toggleArrayFilter({}, "status", "running");
    expect(next.status).toEqual(["running"]);
  });

  it("removes a value already present", () => {
    const next = toggleArrayFilter({ status: ["running", "failed"] }, "status", "running");
    expect(next.status).toEqual(["failed"]);
  });

  it("clears experimentId when projectId changes", () => {
    const next = toggleArrayFilter({ projectId: ["A"], experimentId: ["e1"] }, "projectId", "B");
    expect(next.projectId).toEqual(["A", "B"]);
    expect(next.experimentId).toBeUndefined();
  });
});

describe("toggleStarted", () => {
  it("adds and removes a window, clearing the field when empty", () => {
    expect(toggleStarted({}, "24h").started).toEqual(["24h"]);
    expect(toggleStarted({ started: ["24h"] }, "24h").started).toBeUndefined();
  });
});

describe("absorbFacetTokens", () => {
  it("turns facet tokens into picks and keeps the rest as free tokens", () => {
    const next = absorbFacetTokens({}, "status:failed,interrupted project:NVE target:laptop nve", [
      { id: "nve-drift", name: "NVE" },
    ]);
    expect(next).toEqual({
      status: ["failed", "interrupted"],
      projectId: ["nve-drift"],
      target: ["laptop"],
      q: "nve",
    });
  });
});

describe("hasActiveFilters", () => {
  it("is false for empty filters", () => {
    expect(hasActiveFilters({})).toBe(false);
  });
  it("is true once any filter is set", () => {
    expect(hasActiveFilters({ status: ["running"] })).toBe(true);
    expect(hasActiveFilters({ started: ["7d"] })).toBe(true);
    expect(hasActiveFilters({ q: "nve" })).toBe(true);
  });
});
