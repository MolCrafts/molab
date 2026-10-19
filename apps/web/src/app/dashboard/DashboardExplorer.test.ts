import { describe, expect, it } from "@rstest/core";

import {
  PROJECT_LIMIT,
  projectDetail,
  RUNNING_FAILED_LIMIT,
  selectRunningAndFailed,
} from "@/app/dashboard/DashboardExplorer";
import type { WorkspaceRunRow } from "@/app/runs/types";

const run = (id: string, status: string, createdAt: string): WorkspaceRunRow => ({
  id,
  name: id,
  workspaceKey: "ws",
  path: `projects/project/experiments/experiment/runs/${id}`,
  projectId: "project",
  projectName: "Project",
  experimentId: "experiment",
  experimentName: "Experiment",
  definitionHash: `definition-${id}`,
  experimentRevisionId: "revision-1",
  inputAssetIds: [],
  targetHint: null,
  statusSummary: {
    total: 1,
    active: status === "running" ? 1 : 0,
    notStarted: false,
    byStatus: { [status]: 1 },
  },
  parameters: {},
  createdAt,
  executions: [
    {
      executionId: `execution-${id}`,
      runId: id,
      mode: "initial",
      status,
      createdAt,
      startedAt: createdAt,
      finishedAt: status === "failed" || status === "succeeded" ? createdAt : null,
      durationSeconds: 0,
      basedOnExecutionId: null,
      checkpointArtifactId: null,
      schedulerJobId: null,
      backend: null,
      backendMetadata: {},
    },
  ],
});

describe("selectRunningAndFailed", () => {
  it("keeps failed runs ahead of newer running runs and caps the sample", () => {
    const sample = selectRunningAndFailed([
      run("running-new", "running", "2026-08-30T12:00:00Z"),
      run("done", "succeeded", "2026-08-30T13:00:00Z"),
      run("failed-old", "failed", "2026-08-30T01:00:00Z"),
      run("failed-new", "failed", "2026-08-30T11:00:00Z"),
      run("running-old", "running", "2026-08-30T02:00:00Z"),
      run("queued", "queued", "2026-08-30T14:00:00Z"),
    ]);

    expect(sample.total).toBe(4);
    expect(sample.visible.map((item) => item.id)).toEqual([
      "failed-new",
      "failed-old",
      "running-new",
    ]);
    expect(sample.visible).toHaveLength(RUNNING_FAILED_LIMIT);
    expect(PROJECT_LIMIT).toBe(6);
  });

  it("names a project's experiment count without a false plural", () => {
    expect(projectDetail("Cooling study", 4)).toBe("Cooling study");
    expect(projectDetail("", 1)).toBe("1 experiment");
    expect(projectDetail("", 0)).toBe("No experiments yet");
    expect(projectDetail("", 3)).toBe("3 experiments");
    expect(projectDetail("", null)).toBe("");
  });
});
