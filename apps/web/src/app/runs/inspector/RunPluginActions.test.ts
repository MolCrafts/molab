import { describe, expect, it } from "@rstest/core";
import type { WorkspaceRunRow } from "../types";
import { collectRunPluginActions, runSummaryForPluginMatching } from "./RunPluginActions";

describe("RunPluginActions", () => {
  it("collects contextual plugin tabs once and preserves their route values", () => {
    expect(
      collectRunPluginActions(
        [{ id: "molq:run-tab", value: "molq", label: "Molq" }],
        [
          { id: "molplot:run-metrics", value: "metrics", label: "Metrics" },
          { id: "molvis:run-tab", value: "molvis", label: "MolVis" },
          { id: "future:run-tab", value: "future-tool", label: "Future tool" },
          { id: "duplicate", value: "metrics", label: "Metrics duplicate" },
        ],
      ).map(({ id, value, label }) => ({ id, value, label })),
    ).toEqual([
      { id: "molq:run-tab", value: "molq", label: "Molq" },
      { id: "duplicate", value: "metrics", label: "Metrics duplicate" },
      { id: "molvis:run-tab", value: "molvis", label: "MolVis" },
      { id: "future:run-tab", value: "future-tool", label: "Future tool" },
    ]);
  });

  it("adapts workspace rows for backend plugin matching without a loaded project tree", () => {
    const row: WorkspaceRunRow = {
      id: "run-1",
      name: "Run 1",
      projectId: "project-1",
      projectName: "Project 1",
      experimentId: "experiment-1",
      experimentName: "Experiment 1",
      status: "running",
      backend: "molq",
      cluster: "dardel",
      scheduler: "slurm",
      target: "gpu",
      profile: "dardel-gpu",
      parameters: {},
      createdAt: "2026-09-01T10:00:00Z",
      finishedAt: null,
      executionCount: 0,
      latestSchedulerJobId: "1234",
      executions: [],
    };

    const summary = runSummaryForPluginMatching(row);
    expect(summary.executorInfo).toMatchObject({
      backend: "molq",
      cluster: "dardel",
      scheduler: "slurm",
      scheduler_job_id: "1234",
    });
  });
});
