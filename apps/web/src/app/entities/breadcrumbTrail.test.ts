import { describe, expect, it } from "@rstest/core";
import type { WorkspaceSnapshot } from "@/app/types";
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
      executionHistory: [{ executionId: "e01" }, { executionId: "e02" }],
    },
  ],
  workflows: [],
  assets: [{ id: "a1", name: "trajectory.xyz" }],
} as unknown as WorkspaceSnapshot;

describe("buildTrail", () => {
  it("walks a run from its project down to the latest attempt", () => {
    const trail = buildTrail({ objectType: "run", objectId: "r1" }, "projects", snapshot);
    expect(trail.map((item) => [item.kind, item.label])).toEqual([
      ["project", "NVE Drift"],
      ["experiment", "Integrator Benchmark"],
      ["run", "ase · nve · 2 fs"],
      ["attempt", "e02"],
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

  it("has no trail for a section page", () => {
    expect(buildTrail(null, "runs", snapshot)).toEqual([]);
  });
});
