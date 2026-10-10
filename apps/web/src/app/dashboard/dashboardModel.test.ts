import { describe, expect, it } from "@rstest/core";
import { buildDashboardModel } from "@/app/dashboard/dashboardModel";
import type { WorkspaceRunRow } from "@/app/runs/types";
import type { WorkspaceSnapshot } from "@/app/types";

const snapshot: WorkspaceSnapshot = {
  workspaces: [],
  projects: [],
  experiments: [],
  runs: [],
  assets: [],
  workflows: [],
  workspaceRoot: null,
  consoleEntries: [],
};

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
    active: status === "running" || status === "queued" ? 1 : 0,
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

describe("buildDashboardModel", () => {
  it("separates actionable failures, active runs, and recent completed work", () => {
    const model = buildDashboardModel(snapshot, [
      run("completed", "succeeded", "2026-08-30T09:00:00Z"),
      run("active", "running", "2026-08-30T10:00:00Z"),
      run("failed", "failed", "2026-08-30T11:00:00Z"),
    ]);

    expect(model.attention.map((item) => item.id)).toEqual(["failed-run-failed"]);
    expect(model.activeRuns.map((item) => item.id)).toEqual(["active"]);
    expect(model.recentItems.map((item) => item.id)).toEqual(["run-completed"]);
  });

  it("surfaces data completeness before failed-run overflow", () => {
    const model = buildDashboardModel(
      snapshot,
      Array.from({ length: 7 }, (_, index) =>
        run(`failed-${index}`, "failed", `2026-08-30T0${index}:00:00Z`),
      ),
      { truncated: true },
    );

    expect(model.attention[0]?.id).toBe("runs-truncated");
    expect(model.attention).toHaveLength(5);
    expect(model.hiddenAttentionCount).toBe(3);
  });

  it("treats unreachable workspaces as operational attention", () => {
    const model = buildDashboardModel(
      {
        ...snapshot,
        workspaces: [
          {
            key: "remote",
            label: "Remote lab",
            isRemote: true,
            path: null,
            active: true,
            unreachable: true,
          },
        ],
      },
      [],
    );

    expect(model.attention[0]).toMatchObject({
      id: "workspace-remote",
      href: "/settings",
      tone: "critical",
    });
  });

  it("links overflow only when hidden items share one destination", () => {
    const failedOnly = buildDashboardModel(
      snapshot,
      Array.from({ length: 6 }, (_, index) =>
        run(`failed-${index}`, "failed", `2026-08-30T0${index}:00:00Z`),
      ),
    );
    expect(failedOnly.attentionOverflow).toEqual({ label: "View 1 more", href: "/runs" });

    const mixed = buildDashboardModel(
      {
        ...snapshot,
        workspaces: Array.from({ length: 6 }, (_, index) => ({
          key: `remote-${index}`,
          label: `Remote ${index}`,
          isRemote: true,
          path: null,
          active: false,
          unreachable: true,
        })),
      },
      Array.from({ length: 2 }, (_, index) =>
        run(`failed-${index}`, "failed", `2026-08-30T0${index}:00:00Z`),
      ),
    );
    expect(mixed.attentionOverflow).toEqual({ label: "View 3 more", href: null });
  });
});
