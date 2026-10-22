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
  kind: "data" | "failed-run" | "workspace";
  title: string;
  detail: string;
  href?: string;
  retry?: "runs";
  actionLabel: string;
  tone: "critical" | "warning";
}

export interface DashboardAttentionOverflow {
  label: string;
  href: string | null;
}

export interface DashboardRecentItem {
  id: string;
  type: "Project" | "Experiment" | "Run";
  title: string;
  detail: string;
  href: string;
  timestamp: string;
  /** Presentation status for a run. Projects and experiments have none. */
  status: string | null;
}

export interface DashboardModel {
  attention: DashboardAttentionItem[];
  hiddenAttentionCount: number;
  attentionOverflow: DashboardAttentionOverflow | null;
  /** Auth, reachability, and a failed poll. Not capped by failed-run rows. */
  operational: DashboardAttentionItem[];
  operationalOverflow: DashboardAttentionOverflow | null;
  /** Failed runs only. Operational rows do not consume this cap. */
  failed: DashboardAttentionItem[];
  failedOverflow: DashboardAttentionOverflow | null;
  activeRuns: WorkspaceRunRow[];
  hiddenActiveCount: number;
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

export interface DashboardInventoryOptions {
  runsError?: string | null;
  truncated?: boolean;
  /** Workspace keys whose run page failed this poll, even if the snapshot still looks reachable. */
  unreachableKeys?: readonly string[];
}

/** True when a chart must not claim the lab is quiet. Truncation alone is still usable data. */
export const isInventoryBlocked = (
  snapshot: WorkspaceSnapshot,
  options: DashboardInventoryOptions = {},
): boolean =>
  Boolean(options.runsError) ||
  (options.unreachableKeys?.length ?? 0) > 0 ||
  snapshot.workspaces.some((workspace) => workspace.unreachable || workspace.needsAuth);

/** Placeholder for a widget that has nothing to draw because the inventory is incomplete. */
export const WIDGET_HOLD_COPY = "Not shown while the run list is incomplete.";

export const widgetEmptyCopy = (blocked: boolean, ready: string): string =>
  blocked ? WIDGET_HOLD_COPY : ready;

/** Skeleton until the first successful poll, unless a known blocker should stay visible. */
export const showDashboardSkeleton = ({
  loading,
  rowCount,
  synced,
  blocked,
}: {
  loading: boolean;
  rowCount: number;
  synced: boolean;
  blocked: boolean;
}): boolean => rowCount === 0 && !blocked && (loading || !synced);

/** Charts of an empty, blocked inventory would only repeat the all-clear. */
export const showDashboardGrid = (blocked: boolean, rowCount: number): boolean =>
  !blocked || rowCount > 0;

/** An execution exists, so the instruments have something to measure. */
export const hasMeasurableExecutions = (rows: readonly WorkspaceRunRow[]): boolean =>
  rows.some((run) => run.statusSummary.total > 0 || run.executions.length > 0);

/**
 * The Workspace rail section is the dashboard. Keep it until the first successful
 * poll, and while the inventory is blocked. Hide it when that poll has nothing
 * to measure. `loading` is ignored after the first sync so a refresh does not
 * flash the section back.
 */
export const showWorkspaceTab = ({
  synced,
  blocked,
  measurable,
}: {
  synced: boolean;
  blocked: boolean;
  measurable: boolean;
}): boolean => {
  if (!synced || blocked) return true;
  return measurable;
};

/** The truncation strip supplements a partial but readable inventory. A failed poll hides it. */
export const showTruncationStrip = (truncated: boolean, runsError: string | null): boolean =>
  truncated && !runsError;

const overflowFor = (
  hidden: ReadonlyArray<{ overflowHref: string }>,
): DashboardAttentionOverflow | null => {
  if (hidden.length === 0) return null;
  const destinations = new Set(hidden.map(({ overflowHref }) => overflowHref));
  return {
    label: `View ${hidden.length} more`,
    href: destinations.size === 1 ? ([...destinations][0] ?? null) : null,
  };
};

const isOperational = (item: DashboardAttentionItem): boolean =>
  item.kind === "workspace" || item.id === "runs-unavailable";

export const buildDashboardModel = (
  snapshot: WorkspaceSnapshot,
  runs: WorkspaceRunRow[],
  options: DashboardInventoryOptions = {},
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
          ? "Sign in again from Settings to resume this workspace."
          : "Check the connection in Settings.",
        href: "/settings",
        actionLabel: "Open settings",
        tone: "critical",
      },
      450,
      "/settings",
    );
  }

  const flaggedKeys = new Set(
    snapshot.workspaces
      .filter((workspace) => workspace.unreachable || workspace.needsAuth)
      .map((workspace) => workspace.key),
  );
  for (const key of options.unreachableKeys ?? []) {
    if (flaggedKeys.has(key)) continue;
    const known = snapshot.workspaces.find((workspace) => workspace.key === key);
    const label = known?.label || key || "This workspace";
    addAttention(
      {
        id: `runs-unreachable-${key || "active"}`,
        kind: "workspace",
        title: `${label} did not return runs`,
        detail: "This workspace was left out of the run list.",
        retry: "runs",
        actionLabel: "Retry",
        tone: "critical",
      },
      440,
      "/runs",
    );
  }

  if (options.truncated) {
    addAttention(
      {
        id: "runs-truncated",
        kind: "data",
        title: "Run inventory is truncated",
        detail: "The run list is incomplete. Narrow the filters in Runs to see the rest.",
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
        id: `failed-run-${run.workspaceKey}:${run.id}`,
        kind: "failed-run",
        title: run.name || run.id,
        detail: `${run.projectName} · ${run.experimentName}`,
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
  const operationalRanked = rankedAttention.filter(({ item }) => isOperational(item));
  const visibleAttention = rankedAttention.slice(0, MAX_ATTENTION_ITEMS).map(({ item }) => item);
  const hiddenAttention = rankedAttention.slice(MAX_ATTENTION_ITEMS);
  const attentionOverflow = overflowFor(hiddenAttention);
  const operational = operationalRanked.slice(0, MAX_ATTENTION_ITEMS).map(({ item }) => item);
  const operationalOverflow = overflowFor(operationalRanked.slice(MAX_ATTENTION_ITEMS));
  const failedRanked = rankedAttention.filter(({ item }) => item.kind === "failed-run");
  const failed = failedRanked.slice(0, MAX_ATTENTION_ITEMS).map(({ item }) => item);
  const failedOverflow = overflowFor(failedRanked.slice(MAX_ATTENTION_ITEMS));
  const activeSorted = runs
    .filter((run) => {
      return run.statusSummary.active > 0;
    })
    .sort(newestRunsFirst);
  const activeRuns = activeSorted.slice(0, MAX_ACTIVE_RUNS);
  const hiddenActiveCount = activeSorted.length - activeRuns.length;

  const recentItems: DashboardRecentItem[] = [
    ...snapshot.projects.map((project) => ({
      id: `project-${project.id}`,
      type: "Project" as const,
      title: project.name,
      detail: project.summary || "Project",
      href: projectPath(project.id),
      timestamp: project.updatedAt,
      status: null,
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
      status: null,
    })),
    ...runs
      .filter((run) => {
        const group = groupForStatus(runPresentationStatus(run));
        return group !== "running" && group !== "pending" && group !== "failed";
      })
      .map((run) => ({
        id: `run-${run.workspaceKey}:${run.id}`,
        type: "Run" as const,
        title: run.name || run.id,
        detail: `${run.projectName} · ${run.experimentName}`,
        href: runPath(run.projectId, run.experimentId, run.id),
        timestamp: runActivityTimestamp(run),
        status: runPresentationStatus(run),
      })),
  ]
    .sort((left, right) => timestampValue(right.timestamp) - timestampValue(left.timestamp))
    .slice(0, MAX_RECENT_ITEMS);

  return {
    attention: visibleAttention,
    hiddenAttentionCount: hiddenAttention.length,
    attentionOverflow,
    operational,
    operationalOverflow,
    failed,
    failedOverflow,
    activeRuns,
    hiddenActiveCount,
    recentItems,
  };
};
