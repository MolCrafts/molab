import { describe, expect, it } from "@rstest/core";
import {
  buildDashboardModel,
  hasMeasurableExecutions,
  isInventoryBlocked,
  showDashboardGrid,
  showDashboardSkeleton,
  showTruncationStrip,
  showWorkspaceTab,
  WIDGET_HOLD_COPY,
  widgetEmptyCopy,
} from "@/app/dashboard/dashboardModel";
import type { WorkspaceRunRow } from "@/app/runs/types";
import type { WorkspaceSnapshot } from "@/app/types";

const snapshot: WorkspaceSnapshot = {
  workspaces: [],
  serveScope: null,
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

    expect(model.attention.map((item) => item.id)).toEqual(["failed-run-ws:failed"]);
    expect(model.failed.map((item) => item.id)).toEqual(["failed-run-ws:failed"]);
    expect(model.failed[0]?.detail).toBe("Project · Experiment");
    expect(model.activeRuns.map((item) => item.id)).toEqual(["active"]);
    expect(model.hiddenActiveCount).toBe(0);
    expect(model.recentItems.map((item) => item.id)).toEqual(["run-ws:completed"]);
    expect(model.recentItems[0]?.status).toBe("succeeded");
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
    expect(model.failed).toHaveLength(5);
    expect(model.failed.every((item) => item.kind === "failed-run")).toBe(true);
    expect(model.failedOverflow).toEqual({ label: "View 2 more", href: "/runs" });
    expect(model.failed.some((item) => item.id === "failed-run-ws:failed-0")).toBe(false);
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
    expect(failedOnly.failed).toHaveLength(5);
    expect(failedOnly.failedOverflow).toEqual({ label: "View 1 more", href: "/runs" });

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
    expect(mixed.failed).toHaveLength(2);
    expect(mixed.failedOverflow).toBeNull();
  });

  it("ranks a failed poll and a dead remote above a quiet empty inventory", () => {
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
            unreachable: false,
            needsAuth: true,
          },
        ],
      },
      [run("failed", "failed", "2026-08-30T11:00:00Z")],
      { runsError: "Failed to fetch", unreachableKeys: ["remote", "bench"] },
    );

    expect(model.operational.map((item) => item.id)).toEqual([
      "runs-unavailable",
      "workspace-remote",
      "runs-unreachable-bench",
    ]);
    expect(model.operational[0]).toMatchObject({ retry: "runs", actionLabel: "Retry" });
    expect(model.operational[1]).toMatchObject({
      title: "Remote lab needs authentication",
      detail: "Sign in again from Settings to resume this workspace.",
      href: "/settings",
      actionLabel: "Open settings",
    });
    expect(model.operational[2]).toMatchObject({
      title: "bench did not return runs",
      detail: "This workspace was left out of the run list.",
      retry: "runs",
    });
    expect(model.operationalOverflow).toBeNull();
  });

  it("keeps extra dead remotes off the failed-run cap", () => {
    const model = buildDashboardModel(
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
      [run("failed", "failed", "2026-08-30T11:00:00Z")],
    );

    expect(model.operational).toHaveLength(5);
    expect(model.operational.every((item) => item.kind === "workspace")).toBe(true);
    expect(model.operationalOverflow).toEqual({ label: "View 1 more", href: "/settings" });
    expect(model.attention.some((item) => item.id === "failed-run-ws:failed")).toBe(false);
    expect(model.failed.map((item) => item.id)).toEqual(["failed-run-ws:failed"]);
    expect(model.failedOverflow).toBeNull();
  });

  it("reports active runs past the visible cap", () => {
    const model = buildDashboardModel(
      snapshot,
      Array.from({ length: 11 }, (_, index) =>
        run(`active-${index}`, "running", `2026-08-30T${String(index).padStart(2, "0")}:00:00Z`),
      ),
    );

    expect(model.activeRuns).toHaveLength(10);
    expect(model.hiddenActiveCount).toBe(1);
    expect(model.activeRuns.some((item) => item.id === "active-0")).toBe(false);
  });

  it("does not treat a truncated inventory as a blocked one", () => {
    expect(isInventoryBlocked(snapshot, { truncated: true })).toBe(false);
    expect(isInventoryBlocked(snapshot, { runsError: "Failed to fetch" })).toBe(true);
    expect(showTruncationStrip(true, null)).toBe(true);
    expect(showTruncationStrip(true, "Failed to fetch")).toBe(false);
    expect(showDashboardGrid(true, 0)).toBe(false);
    expect(showDashboardGrid(true, 2)).toBe(true);
    expect(showDashboardGrid(false, 0)).toBe(true);
    expect(widgetEmptyCopy(true, "No runs need attention")).toBe(WIDGET_HOLD_COPY);
    expect(widgetEmptyCopy(false, "No runs need attention")).toBe("No runs need attention");
    expect(
      showDashboardSkeleton({ loading: false, rowCount: 0, synced: false, blocked: false }),
    ).toBe(true);
    expect(
      showDashboardSkeleton({ loading: false, rowCount: 0, synced: false, blocked: true }),
    ).toBe(false);
  });

  it("hides the workspace tab when a synced inventory has no executions", () => {
    const idle = {
      ...run("ddbf4f35", "pending", "2026-10-12T16:36:58Z"),
      statusSummary: { total: 0, active: 0, notStarted: true, byStatus: {} },
      executions: [],
    };

    expect(hasMeasurableExecutions([idle])).toBe(false);
    expect(hasMeasurableExecutions([run("done", "succeeded", "2026-10-12T16:36:58Z")])).toBe(true);
    expect(showWorkspaceTab({ synced: false, blocked: false, measurable: false })).toBe(true);
    expect(showWorkspaceTab({ synced: true, blocked: true, measurable: false })).toBe(true);
    expect(showWorkspaceTab({ synced: true, blocked: false, measurable: false })).toBe(false);
    expect(showWorkspaceTab({ synced: true, blocked: false, measurable: true })).toBe(true);
  });
});
