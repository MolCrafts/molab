import type { PendingApprovalItem } from "@/api/generated/models/PendingApprovalItem";
import { pendingApprovalPath, pendingApprovalTitle } from "@/app/approvals/presentation";
import { experimentPath, projectPath, runPath } from "@/app/entities/paths";
import { runActivityAt, runPresentationStatus } from "@/app/runs/projections";
import { groupForStatus } from "@/app/runs/statusGroups";
import type { WorkspaceRunRow } from "@/app/runs/types";
import type { WorkspaceSnapshot } from "@/app/types";

const MAX_ATTENTION_ITEMS = 5;
const MAX_ACTIVE_RUNS = 10;
const MAX_RECENT_ITEMS = 5;

export interface DashboardAttentionItem {
  id: string;
  kind: "approval" | "data" | "failed-run" | "workspace";
  title: string;
  detail: string;
  href?: string;
  retry?: "approvals" | "runs";
  actionLabel: string;
  tone: "critical" | "warning";
}

export interface DashboardAttentionOverflow {
  label: string;
  href: string | null;
}

export interface DashboardRecentItem {
  id: string;
  type: "Agent task" | "Project" | "Experiment" | "Run";
  title: string;
  detail: string;
  href: string;
  timestamp: string;
}

export interface DashboardModel {
  attention: DashboardAttentionItem[];
  hiddenAttentionCount: number;
  attentionOverflow: DashboardAttentionOverflow | null;
  activeRuns: WorkspaceRunRow[];
  recentItems: DashboardRecentItem[];
}

const timestampValue = (value: string | null | undefined): number => {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
};

export const runActivityTimestamp = (run: WorkspaceRunRow): string => {
  return runActivityAt(run);
};

const newestRunsFirst = (left: WorkspaceRunRow, right: WorkspaceRunRow): number =>
  timestampValue(runActivityTimestamp(right)) - timestampValue(runActivityTimestamp(left));

export const buildDashboardModel = (
  snapshot: WorkspaceSnapshot,
  runs: WorkspaceRunRow[],
  options: {
    approvalsError?: string | null;
    pendingApprovals?: PendingApprovalItem[];
    runsError?: string | null;
    truncated?: boolean;
  } = {},
): DashboardModel => {
  const rankedAttention: Array<{
    item: DashboardAttentionItem;
    overflowHref: string;
    priority: number;
    timestamp: number;
  }> = [];

  const addAttention = (
    item: DashboardAttentionItem,
    priority: number,
    overflowHref: string,
    timestamp = 0,
  ): void => {
    rankedAttention.push({ item, overflowHref, priority, timestamp });
  };

  if (options.runsError) {
    addAttention(
      {
        id: "runs-unavailable",
        kind: "data",
        title: "Runs are unavailable",
        detail: options.runsError,
        retry: "runs",
        actionLabel: "Retry",
        tone: "critical",
      },
      500,
      "/runs",
    );
  }

  if (options.approvalsError) {
    addAttention(
      {
        id: "approvals-unavailable",
        kind: "data",
        title: "Approvals are unavailable",
        detail: options.approvalsError,
        retry: "approvals",
        actionLabel: "Retry",
        tone: "critical",
      },
      490,
      "/agent-tasks",
    );
  }

  for (const workspace of snapshot.workspaces) {
    if (!workspace.unreachable && !workspace.needsAuth) continue;
    addAttention(
      {
        id: `workspace-${workspace.key}`,
        kind: "workspace",
        title: workspace.needsAuth
          ? `${workspace.label} needs authentication`
          : `${workspace.label} is unreachable`,
        detail: workspace.needsAuth
          ? "Reconnect the remote workspace to resume data access."
          : "Check the remote workspace connection and retry.",
        href: "/settings",
        actionLabel: "Open settings",
        tone: "critical",
      },
      450,
      "/settings",
    );
  }

  for (const approval of options.pendingApprovals ?? []) {
    addAttention(
      {
        id: `approval-${approval.taskId}-${approval.requestId}`,
        kind: "approval",
        title: pendingApprovalTitle(approval),
        detail: `${approval.projectId}/${approval.experimentId} · waiting for your decision`,
        href: pendingApprovalPath(approval),
        actionLabel: "Review",
        tone: "warning",
      },
      400,
      "/agent-tasks",
      timestampValue(approval.requestedAt),
    );
  }

  if (options.truncated) {
    addAttention(
      {
        id: "runs-truncated",
        kind: "data",
        title: "Run inventory is truncated",
        detail:
          "Dashboard results may be incomplete. Narrow the Runs filters to inspect the full set.",
        href: "/runs",
        actionLabel: "Open runs",
        tone: "warning",
      },
      350,
      "/runs",
    );
  }

  const failedRuns = runs
    .filter((run) => groupForStatus(runPresentationStatus(run)) === "failed")
    .sort(newestRunsFirst);
  for (const run of failedRuns) {
    addAttention(
      {
        id: `failed-run-${run.id}`,
        kind: "failed-run",
        title: run.name || run.id,
        detail: `${run.projectName} · ${run.experimentName} · failed`,
        href: runPath(run.projectId, run.experimentId, run.id),
        actionLabel: "Inspect",
        tone: "critical",
      },
      300,
      "/runs",
      timestampValue(runActivityTimestamp(run)),
    );
  }

  rankedAttention.sort(
    (left, right) =>
      right.priority - left.priority ||
      right.timestamp - left.timestamp ||
      left.item.id.localeCompare(right.item.id),
  );
  const visibleAttention = rankedAttention.slice(0, MAX_ATTENTION_ITEMS).map(({ item }) => item);
  const hiddenAttention = rankedAttention.slice(MAX_ATTENTION_ITEMS);
  const hiddenDestinations = new Set(hiddenAttention.map(({ overflowHref }) => overflowHref));
  const attentionOverflow: DashboardAttentionOverflow | null =
    hiddenAttention.length === 0
      ? null
      : {
          label: `View ${hiddenAttention.length} more`,
          href: hiddenDestinations.size === 1 ? ([...hiddenDestinations][0] ?? null) : null,
        };
  const activeRuns = runs
    .filter((run) => {
      return run.statusSummary.active > 0;
    })
    .sort(newestRunsFirst)
    .slice(0, MAX_ACTIVE_RUNS);

  const recentItems: DashboardRecentItem[] = [
    ...snapshot.projects.map((project) => ({
      id: `project-${project.id}`,
      type: "Project" as const,
      title: project.name,
      detail: project.summary || "Project",
      href: projectPath(project.id),
      timestamp: project.updatedAt,
    })),
    ...snapshot.experiments.map((experiment) => ({
      id: `experiment-${experiment.id}`,
      type: "Experiment" as const,
      title: experiment.name,
      detail:
        snapshot.projects.find((project) => project.id === experiment.projectId)?.name ??
        "Experiment",
      href: experimentPath(experiment.projectId, experiment.id),
      timestamp: experiment.updatedAt,
    })),
    ...snapshot.agentSessions.map((session) => ({
      id: `agent-${session.id}`,
      type: "Agent task" as const,
      title: session.title,
      detail: session.status.replace(/_/g, " "),
      href: `/agent-tasks/${encodeURIComponent(session.id)}`,
      timestamp: session.createdAt,
    })),
    ...runs
      .filter((run) => {
        const group = groupForStatus(runPresentationStatus(run));
        return group !== "running" && group !== "pending" && group !== "failed";
      })
      .map((run) => ({
        id: `run-${run.id}`,
        type: "Run" as const,
        title: run.name || run.id,
        detail: `${run.projectName} · ${run.experimentName}`,
        href: runPath(run.projectId, run.experimentId, run.id),
        timestamp: runActivityTimestamp(run),
      })),
  ]
    .sort((left, right) => timestampValue(right.timestamp) - timestampValue(left.timestamp))
    .slice(0, MAX_RECENT_ITEMS);

  return {
    attention: visibleAttention,
    hiddenAttentionCount: hiddenAttention.length,
    attentionOverflow,
    activeRuns,
    recentItems,
  };
};
