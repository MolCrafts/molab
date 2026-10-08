import { ArrowUpRight, LayoutDashboard, TriangleAlert } from "lucide-react";
import { type JSX, type ReactNode, useMemo } from "react";
import { Link } from "react-router-dom";

import {
  DashboardCanvas,
  DashboardCard,
  EntityPage,
  Histogram,
  Schedule,
  type ScheduleItem,
  StatusBreakdown,
  StatusDistribution,
  StatusLegend,
} from "@/app/components/entity";
import { runPath } from "@/app/entities/paths";
import {
  runActivityAt,
  runExecutorFacet,
  runFinishedAt,
  runPresentationStatus,
  runStartedAt,
} from "@/app/runs/projections";
import { groupForStatus, type StatusGroupId } from "@/app/runs/statusGroups";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { useWorkspaceRuns } from "@/app/runs/useWorkspaceRuns";
import type { WorkspaceSnapshot } from "@/app/types";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { formatDuration, formatRelative } from "@/lib/format-time";

interface DashboardPageProps {
  snapshot: WorkspaceSnapshot;
}

interface ExecutionRollup {
  total: number;
  running: number;
  pending: number;
  succeeded: number;
  failed: number;
  cancelled: number;
}

const emptyRollup = (): ExecutionRollup => ({
  total: 0,
  running: 0,
  pending: 0,
  succeeded: 0,
  failed: 0,
  cancelled: 0,
});

/** Every count on this page is an *execution* count — a run has N attempts. */
const rollupExecutions = (rows: WorkspaceRunRow[]): ExecutionRollup => {
  const counts = emptyRollup();
  for (const run of rows) {
    for (const execution of run.executions) {
      const group = groupForStatus(execution.status);
      counts.total += 1;
      if (group) counts[group] += 1;
    }
  }
  return counts;
};

const timestamp = (value: string | null | undefined): number | null => {
  const parsed = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
};

/** Wall-clock seconds a run occupied, for finished runs only. */
const runDurationSeconds = (run: WorkspaceRunRow): number | null => {
  const start = timestamp(runStartedAt(run));
  const end = timestamp(runFinishedAt(run));
  if (start === null || end === null || end < start) return null;
  return (end - start) / 1000;
};

/**
 * Workspace posture: the status mix of every attempt, once. The page meta
 * already states the execution total, so the bar does not repeat it.
 */
const ExecutionStatus = ({ counts }: { counts: ExecutionRollup }): JSX.Element => (
  <StatusDistribution counts={counts} unit="executions" />
);

const ACTIVITY_BUCKETS = 12;
const ACTIVITY_WINDOW_MS = 24 * 60 * 60 * 1000;

/**
 * Executions *touched* per two-hour bucket over the last day. The previous
 * version plotted run creation, which says nothing about whether the workspace
 * is busy — a swept experiment creates 200 runs in one second.
 */
const ActivityPlot = ({ rows }: { rows: WorkspaceRunRow[] }): JSX.Element => {
  const { bars, peak } = useMemo(() => {
    const now = Date.now();
    const width = ACTIVITY_WINDOW_MS / ACTIVITY_BUCKETS;
    const values = new Array<number>(ACTIVITY_BUCKETS).fill(0);
    for (const run of rows) {
      for (const execution of run.executions) {
        for (const instant of [execution.startedAt, execution.finishedAt]) {
          const at = timestamp(instant);
          if (at === null) continue;
          const index = ACTIVITY_BUCKETS - 1 - Math.floor((now - at) / width);
          if (index >= 0 && index < values.length) values[index] += 1;
        }
      }
    }
    return {
      peak: Math.max(...values),
      bars: values.map((value, index) => ({
        id: `h${(index - (ACTIVITY_BUCKETS - 1)) * 2}`,
        value,
      })),
    };
  }, [rows]);

  if (peak === 0) {
    return (
      <p className="text-micro text-muted-foreground">No execution activity in the last 24 hours</p>
    );
  }

  return (
    <div className="space-y-2">
      <div
        role="img"
        aria-label={`Execution starts and finishes per 2 hours over the last day; busiest bucket ${peak}`}
        className="flex h-16 items-end gap-hairline"
      >
        {bars.map((bar) => (
          <span
            key={bar.id}
            title={`${bar.value} execution events`}
            className="flex-1 rounded-t-[2px] bg-accent/40"
            style={{ height: `${Math.max(bar.value > 0 ? 6 : 2, (bar.value / peak) * 100)}%` }}
          />
        ))}
      </div>
      <div className="flex justify-between font-mono text-micro tabular-nums text-muted-foreground">
        <span>−24h</span>
        <span>peak {peak}</span>
        <span>now</span>
      </div>
    </div>
  );
};

/** Which backend is producing the failures — a mix per backend, not a bar of totals. */
const Backends = ({ rows }: { rows: WorkspaceRunRow[] }): JSX.Element => {
  const groups = useMemo(() => {
    const byBackend = new Map<string, WorkspaceRunRow[]>();
    for (const run of rows) {
      const backends = runExecutorFacet(run, "backend");
      for (const backend of backends.length > 0 ? backends : ["unassigned"]) {
        const bucket = byBackend.get(backend) ?? [];
        bucket.push(run);
        byBackend.set(backend, bucket);
      }
    }
    return [...byBackend.entries()]
      .map(([backend, backendRuns]) => ({
        id: backend,
        label: backend,
        counts: rollupExecutions(backendRuns),
      }))
      .sort((left, right) => right.counts.total - left.counts.total)
      .slice(0, 6);
  }, [rows]);

  if (groups.length === 0) {
    return <p className="text-micro text-muted-foreground">No executor recorded yet</p>;
  }
  return <StatusBreakdown groups={groups} />;
};

/** The one list on this page the reader is meant to click, not scan. */
const NeedsAttention = ({ rows }: { rows: WorkspaceRunRow[] }): JSX.Element => {
  const failures = rows
    .filter((run) => groupForStatus(runPresentationStatus(run)) === "failed")
    .sort(
      (left, right) =>
        (timestamp(runActivityAt(right)) ?? 0) - (timestamp(runActivityAt(left)) ?? 0),
    )
    .slice(0, 6);

  if (failures.length === 0) {
    return <p className="text-micro text-muted-foreground">No failed runs</p>;
  }
  return (
    <ul className="divide-y divide-border/50">
      {failures.map((run) => (
        <li key={run.id}>
          <Link
            to={runPath(run.projectId, run.experimentId, run.id)}
            className="flex min-w-0 items-center gap-2 py-row-pad hover:bg-interactive"
          >
            <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-status-failed" />
            <span className="min-w-0 flex-1 truncate text-micro text-status-failed-foreground">
              {run.name || run.id}
            </span>
            <span className="shrink-0 text-micro text-status-failed-foreground">Failed</span>
            <span className="shrink-0 font-mono text-micro text-muted-foreground">
              {formatRelative(runActivityAt(run))}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
};

const scheduleItems = (rows: WorkspaceRunRow[]): ScheduleItem[] =>
  [...rows]
    .sort(
      (left, right) =>
        (timestamp(runActivityAt(right)) ?? 0) - (timestamp(runActivityAt(left)) ?? 0),
    )
    .slice(0, 8)
    .map((run) => ({
      id: run.id,
      label: run.name || run.id,
      detail: run.experimentName,
      start: timestamp(runStartedAt(run)),
      end: timestamp(runFinishedAt(run)),
      status: groupForStatus(runPresentationStatus(run)) as StatusGroupId | null,
      render: (children: ReactNode) => (
        <Link
          to={runPath(run.projectId, run.experimentId, run.id)}
          className="block min-w-0 hover:bg-interactive"
        >
          {children}
        </Link>
      ),
    }));

export const DashboardPage = ({ snapshot }: DashboardPageProps): JSX.Element => {
  const { rows, loading, error, lastSyncedAt, refresh, truncated } = useWorkspaceRuns();
  const activeWorkspace =
    snapshot.workspaces.find((workspace) => workspace.active) ?? snapshot.workspaces[0];
  const counts = useMemo(() => rollupExecutions(rows), [rows]);
  const durations = useMemo(
    () => rows.map(runDurationSeconds).filter((value): value is number => value !== null),
    [rows],
  );
  return (
    <EntityPage
      icon={LayoutDashboard}
      title="Dashboard"
      meta={
        <>
          <span>{rows.length} runs</span>
          <span>{counts.total} executions</span>
          {activeWorkspace ? <span>{activeWorkspace.label}</span> : null}
          {lastSyncedAt ? <span>synced {formatRelative(lastSyncedAt.toISOString())}</span> : null}
        </>
      }
      actions={
        <WorkbenchIconAction label="Open runs" kind="primary" size="default" asChild>
          <Link to="/runs">
            <ArrowUpRight className="size-3.5" />
          </Link>
        </WorkbenchIconAction>
      }
    >
      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading && rows.length === 0 ? (
          <WorkbenchOperationState
            kind="loading"
            title="Loading workspace status"
            skeletonRows={5}
          />
        ) : null}
        {error ? (
          <WorkbenchOperationState
            kind="error"
            density="compact"
            title="Could not load dashboard runs"
            detail={error}
            action={<WorkbenchRetryAction onClick={refresh} />}
          />
        ) : null}
        {truncated ? (
          <div className="flex items-center gap-2 border-b border-status-warning/30 bg-status-warning-soft px-4 py-2 text-micro text-status-warning-foreground">
            <TriangleAlert className="size-icon-sm" />
            <span>Run inventory is truncated; open Runs to narrow the dataset.</span>
          </div>
        ) : null}

        {rows.length > 0 ? (
          <DashboardCanvas>
            <div className="grid min-w-0 lg:grid-cols-2">
              <DashboardCard title="Execution status" className="lg:border-r">
                <ExecutionStatus counts={counts} />
              </DashboardCard>
              <DashboardCard title="Activity" description="Last 24 hours">
                <ActivityPlot rows={rows} />
              </DashboardCard>
              <DashboardCard title="Backends" className="lg:border-r">
                <Backends rows={rows} />
                <StatusLegend className="mt-3" />
              </DashboardCard>
              <DashboardCard title="Run duration" description="Finished runs">
                <Histogram
                  values={durations}
                  format={formatDuration}
                  unit="runs"
                  ariaLabel="Distribution of wall-clock duration across finished runs"
                />
                {durations.length === 0 ? (
                  <p className="text-micro text-muted-foreground">No finished runs yet</p>
                ) : null}
              </DashboardCard>
            </div>
            <div className="grid min-w-0 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <DashboardCard
                title="Schedule"
                description="Most recently active"
                className="lg:border-r"
              >
                <Schedule
                  items={scheduleItems(rows)}
                  empty={
                    <p className="text-micro text-muted-foreground">
                      No run has started yet — nothing to place on a timeline.
                    </p>
                  }
                />
              </DashboardCard>
              <DashboardCard title="Needs attention" description="Failed runs">
                <NeedsAttention rows={rows} />
              </DashboardCard>
            </div>
          </DashboardCanvas>
        ) : !loading && !error ? (
          <WorkbenchOperationState
            kind="empty"
            title="No runs yet"
            detail="Open a project or experiment to start tracked work."
          />
        ) : null}
      </div>
    </EntityPage>
  );
};
