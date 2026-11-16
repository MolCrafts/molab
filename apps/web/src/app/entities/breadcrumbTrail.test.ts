import { beforeEach, describe, expect, it } from "@rstest/core";
import type { WorkspaceSnapshot } from "@/app/types";
import { createPluginAPI } from "@/plugins/api/create_api";
import { resetContributionRuntimeForTests } from "@/plugins/contribution-runtime";
import { registerCoreNavigation } from "@/plugins/core/navigation";
import { buildTrail } from "./breadcrumbTrail";

const snapshot = {
  serveScope: null,
  projects: [{ id: "p1", name: "NVE Drift" }],
  experiments: [{ id: "e1", name: "Integrator Benchmark", projectId: "p1" }],
  runs: [
    {
      id: "r1",
      name: "ase · nve · 2 fs",
      projectId: "p1",
      experimentId: "e1",
      executionHistory: [
        { executionId: "e01", mode: "initial" },
        { executionId: "e02", mode: "resume" },
      ],
    },
  ],
  workflows: [],
  assets: [{ id: "a1", name: "trajectory.xyz" }],
} as unknown as WorkspaceSnapshot;

describe("buildTrail", () => {
  beforeEach(() => {
    resetContributionRuntimeForTests();
    registerCoreNavigation(createPluginAPI("core").api);
  });

  it("walks a run from its project down to the latest attempt", () => {
    const trail = buildTrail({ objectType: "run", objectId: "r1" }, "projects", snapshot);
    expect(trail.map((item) => [item.kind, item.label])).toEqual([
      ["project", "NVE Drift"],
      ["experiment", "Integrator Benchmark"],
      ["run", "ase · nve · 2 fs"],
      ["attempt", "#2 · resume"],
    ]);
    // Every ancestor navigates; the attempt opens the run's attempts view.
    expect(trail[0]?.to).toBeTruthy();
    expect(trail[1]?.to).toBeTruthy();
    expect(trail[3]?.to).toContain("tab=executions");
  });

  it("names a run that has no attempt yet without an attempt segment", () => {
    const fresh = {
      ...snapshot,
      runs: [{ ...snapshot.runs[0], executionHistory: [] }],
    } as unknown as WorkspaceSnapshot;
    const trail = buildTrail({ objectType: "run", objectId: "r1" }, "projects", fresh);
    expect(trail.map((item) => item.kind)).toEqual(["project", "experiment", "run"]);
  });

  it("puts a task under its run", () => {
    const trail = buildTrail(
      { objectType: "task", objectId: "md", taskId: "md", runId: "r1" },
      "projects",
      snapshot,
    );
    expect(trail.map((item) => item.kind)).toEqual(["project", "experiment", "run", "task"]);
  });

  it("starts a non-hierarchy entity at its section", () => {
    const trail = buildTrail({ objectType: "asset", objectId: "a1" }, "asset", snapshot);
    expect(trail.map((item) => item.kind)).toEqual(["section", "asset"]);
    expect(trail[1]?.label).toBe("trajectory.xyz");
  });

  it("names an attempt that recorded no mode by its order alone", () => {
    const bare = {
      ...snapshot,
      runs: [
        {
          ...snapshot.runs[0],
          executionHistory: [{ executionId: "e01" }, { executionId: "e02" }],
        },
      ],
    } as unknown as WorkspaceSnapshot;
    const trail = buildTrail({ objectType: "run", objectId: "r1" }, "projects", bare);
    expect(trail.at(-1)?.label).toBe("#2");
  });

  it("names a project with that project alone", () => {
    const trail = buildTrail({ objectType: "project", objectId: "p1" }, "projects", snapshot);
    expect(trail.map((item) => [item.kind, item.label])).toEqual([["project", "NVE Drift"]]);
  });

  it("names a section page with that section alone", () => {
    expect(buildTrail(null, "dashboard", snapshot)).toEqual([
      { kind: "section", label: "Dashboard" },
    ]);
    expect(buildTrail(null, "runs", snapshot)).toEqual([{ kind: "section", label: "Runs" }]);
    expect(buildTrail(null, "settings", snapshot)).toEqual([
      { kind: "section", label: "Settings" },
    ]);
    expect(buildTrail(null, "missing", snapshot)).toEqual([]);
  });
});
