import { describe, expect, it } from "@rstest/core";
import { PendingApprovalItem } from "@/api/generated/models/PendingApprovalItem";
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
  agentSessions: [],
  workspaceRoot: null,
  consoleEntries: [],
};

const run = (id: string, status: string, createdAt: string): WorkspaceRunRow => ({
  id,
  name: id,
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
  executions: [{
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
  }],
});

const approval = (requestId: string, requestedAt: string): PendingApprovalItem => ({
  experimentId: "experiment",
  intent: "approve_experiment_plan",
  projectId: "project",
  reason: "Review the generated plan.",
  requestId,
  requestedAt,
  runId: "",
  taskId: `task-${requestId}`,
  taskKind: PendingApprovalItem.taskKind.PLAN,
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

  it("ranks blocking approvals ahead of completeness warnings and failed runs", () => {
    const model = buildDashboardModel(snapshot, [run("failed", "failed", "2026-08-30T11:00:00Z")], {
      pendingApprovals: [approval("one", "2026-08-30T10:00:00Z")],
      truncated: true,
    });

    expect(model.attention.map((item) => item.id)).toEqual([
      "approval-task-one-one",
      "runs-truncated",
      "failed-run-failed",
    ]);
    expect(model.attention[0]).toMatchObject({
      actionLabel: "Review",
      href: "/agent-tasks/task-one",
      kind: "approval",
      tone: "warning",
    });
  });

  it("sorts approvals by request time within their priority", () => {
    const model = buildDashboardModel(snapshot, [], {
      pendingApprovals: [
        approval("older", "2026-08-30T09:00:00Z"),
        approval("newer", "2026-08-30T11:00:00Z"),
      ],
    });
    expect(model.attention.map((item) => item.id)).toEqual([
      "approval-task-newer-newer",
      "approval-task-older-older",
    ]);
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
      snapshot,
      Array.from({ length: 2 }, (_, index) =>
        run(`failed-${index}`, "failed", `2026-08-30T0${index}:00:00Z`),
      ),
      {
        pendingApprovals: Array.from({ length: 6 }, (_, index) =>
          approval(`approval-${index}`, `2026-08-30T0${index}:30:00Z`),
        ),
      },
    );
    expect(mixed.attentionOverflow).toEqual({ label: "View 3 more", href: null });
  });

  it("includes agent tasks in continue work", () => {
    const model = buildDashboardModel(
      {
        ...snapshot,
        agentSessions: [
          {
            id: "agent-1",
            sessionId: "session-1",
            title: "Review convergence",
            goal: "Review convergence",
            status: "waiting_for_review",
            createdAt: "2026-08-30T12:00:00Z",
            eventCount: 3,
          },
        ],
      },
      [],
    );
    expect(model.recentItems[0]).toMatchObject({
      id: "agent-agent-1",
      type: "Agent task",
      href: "/agent-tasks/agent-1",
    });
  });
});
