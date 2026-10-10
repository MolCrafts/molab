import { describe, expect, it } from "@rstest/core";
import {
  buildExperimentWorkbenchData,
  buildProjectWorkbenchData,
  experimentRunCompleteness,
  projectSnapshotCompleteness,
} from "@/app/renderers/entityWorkbenchData";
import type {
  ExperimentSummary,
  ProjectSummary,
  RunSummary,
  WorkflowSummary,
  WorkspaceSnapshot,
} from "@/app/types";

const project: ProjectSummary = {
  id: "matrix",
  name: "Matrix",
  path: "projects/matrix",
  status: "active",
  summary: "",
  updatedAt: "2026-06-01T00:00:00Z",
};

const experiment = (
  id: string,
  parameterSpace: Record<string, unknown> = {},
): ExperimentSummary => ({
  id,
  name: id,
  path: `projects/${project.id}/experiments/${id}`,
  status: "active",
  summary: "",
  workflowFile: "workflow.json",
  updatedAt: "2026-06-02T00:00:00Z",
  projectId: project.id,
  parameterSpace,
  workflowSource: null,
});

const run = (
  id: string,
  status: RunSummary["status"],
  parameters: Record<string, unknown>,
): RunSummary => ({
  id,
  name: id,
  path: `projects/${project.id}/experiments/series/runs/${id}`,
  status,
  summary: "",
  updatedAt: `2026-06-02T00:0${id.slice(-1)}:00Z`,
  projectId: project.id,
  experimentId: "series",
  definitionHash: `def-${id}`,
  experimentRevisionId: "rev-series",
  statusSummary: { total: 0, active: 0, notStarted: true, byStatus: {} },
  parameters,
  workflowSource: null,
  workflowSnapshot: null,
  startedAt: null,
  finishedAt: null,
  executionHistory: [],
  errorMessage: null,
});

const workflow: WorkflowSummary = {
  id: "wf-series",
  name: "series workflow",
  status: "active",
  summary: "",
  updatedAt: "2026-06-02T00:00:00Z",
  projectId: project.id,
  experimentId: "series",
  graph: {
    task_configs: [
      { id: "param", type: "task" },
      { id: "box", type: "task" },
    ],
    links: [{ from: "param", to: "box", kind: "parallel" }],
  },
};

const snapshot: WorkspaceSnapshot = {
  workspaces: [],
  projects: [project],
  experiments: [
    experiment("series", { mode: ["block", "random"], ratio: [1, 2], salt: [54, 108] }),
    experiment("empty"),
  ],
  runs: [
    run("run-1", "succeeded", { mode: "block", ratio: 1, salt: 54 }),
    run("run-2", "failed", { mode: "random", ratio: 2, salt: 108 }),
    run("run-3", "running", { mode: "block", ratio: 2, salt: 54 }),
  ],
  assets: [
    {
      id: "asset-1",
      name: "out.dat",
      kind: "data",
      status: "active",
      summary: "",
      updatedAt: "2026-06-02T00:00:00Z",
      sizeBytes: 12,
      projectId: project.id,
    },
  ],
  workflows: [workflow],
  workspaceRoot: null,
  consoleEntries: [],
};

describe("buildProjectWorkbenchData", () => {
  it("rolls up project inventory and run statuses", () => {
    const data = buildProjectWorkbenchData(project.id, snapshot);
    expect(data.experiments).toHaveLength(2);
    expect(data.counts).toMatchObject({ total: 3, succeeded: 1, failed: 1, running: 1 });
    expect(data.assetCount).toBe(1);
  });

  it("flags failed, running, empty, and missing-workflow experiments", () => {
    const reasons = buildProjectWorkbenchData(project.id, snapshot).attention.map((item) => [
      item.experiment.id,
      item.reason,
    ]);
    expect(reasons).toContainEqual(["series", "failed"]);
    expect(reasons).toContainEqual(["series", "running"]);
    expect(reasons).toContainEqual(["empty", "missing-workflow"]);
    expect(reasons).toContainEqual(["empty", "empty"]);
  });
});

describe("lazy snapshot completeness", () => {
  it("keeps authoritative totals separate from partially loaded run statuses", () => {
    const experiments = [
      { ...snapshot.experiments[0], runCount: 3 },
      { ...snapshot.experiments[1], runCount: 0 },
    ];
    const partial = projectSnapshotCompleteness(
      { ...project, experimentCount: 2 },
      experiments,
      snapshot.runs.slice(0, 1),
    );

    expect(partial).toEqual({
      experimentCount: 2,
      runCount: 3,
      experimentsComplete: true,
      runsComplete: false,
    });
  });

  it("treats missing server totals as unknown instead of zero", () => {
    expect(projectSnapshotCompleteness(project, snapshot.experiments, snapshot.runs)).toEqual({
      experimentCount: null,
      runCount: null,
      experimentsComplete: false,
      runsComplete: false,
    });
    expect(experimentRunCompleteness(snapshot.experiments[1], 0)).toEqual({
      runCount: null,
      runsComplete: false,
    });
  });

  it("marks an experiment complete only after all reported runs are loaded", () => {
    const summary = { ...snapshot.experiments[0], runCount: 3 };
    expect(experimentRunCompleteness(summary, 2).runsComplete).toBe(false);
    expect(experimentRunCompleteness(summary, 3).runsComplete).toBe(true);
    expect(experimentRunCompleteness(summary, 4).runsComplete).toBe(false);
  });
});

describe("buildExperimentWorkbenchData", () => {
  it("derives parameter axes from declared space and run parameters", () => {
    const data = buildExperimentWorkbenchData(snapshot.experiments[0], snapshot.runs, workflow);
    expect(data.parameterAxes.map((axis) => axis.key)).toEqual(["mode", "ratio", "salt"]);
    expect(data.parameterAxes.find((axis) => axis.key === "mode")?.values).toEqual([
      "block",
      "random",
    ]);
  });

  it("partitions varying vs fixed parameter axes for scientific layers", () => {
    const mixedRuns = [
      run("run-a", "succeeded", { mode: "block", temperature: 300 }),
      run("run-b", "failed", { mode: "random", temperature: 300 }),
    ];
    const data = buildExperimentWorkbenchData(
      experiment("mixed", { mode: ["block", "random"], temperature: 300 }),
      mixedRuns,
      workflow,
    );
    expect(data.varyingAxes.map((axis) => axis.key)).toEqual(["mode"]);
    expect(data.fixedAxes.map((axis) => axis.key)).toEqual(["temperature"]);
    expect(data.fixedAxes[0]?.values).toEqual(["300"]);
  });

  it("summarizes workflow graph and breaks the status mix down per varying axis", () => {
    const data = buildExperimentWorkbenchData(snapshot.experiments[0], snapshot.runs, workflow);
    expect(data.workflowSummary).toMatchObject({
      exists: true,
      taskCount: 2,
      linkCount: 1,
      parallelGroupCount: 1,
    });
    const mode = data.axisBreakdowns.find((axis) => axis.key === "mode");
    expect(mode?.buckets.map((bucket) => bucket.value)).toEqual(["block", "random"]);
  });

  it("keeps a declared sweep value that has produced no runs yet", () => {
    const data = buildExperimentWorkbenchData(
      experiment("partial", { mode: ["block", "random", "spiral"] }),
      [run("run-a", "succeeded", { mode: "block" })],
      workflow,
    );
    const buckets = data.axisBreakdowns[0]?.buckets ?? [];
    expect(buckets.map((bucket) => bucket.value)).toEqual(["block", "random", "spiral"]);
    expect(buckets.map((bucket) => bucket.counts.total)).toEqual([1, 0, 0]);
  });

  it("leaves fixed axes out of the sweep breakdown", () => {
    const data = buildExperimentWorkbenchData(
      experiment("mixed", { mode: ["block", "random"], temperature: 300 }),
      [
        run("run-a", "succeeded", { mode: "block", temperature: 300 }),
        run("run-b", "failed", { mode: "random", temperature: 300 }),
      ],
      workflow,
    );
    expect(data.axisBreakdowns.map((axis) => axis.key)).toEqual(["mode"]);
    expect(data.axisBreakdowns[0]?.buckets).toEqual([
      { value: "block", counts: expect.objectContaining({ total: 1, succeeded: 1 }) },
      { value: "random", counts: expect.objectContaining({ total: 1, failed: 1 }) },
    ]);
  });
});
