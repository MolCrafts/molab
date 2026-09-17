import { Gauge, LayoutDashboard, Play, TriangleAlert } from "lucide-react";
import { type JSX, type ReactNode, useMemo } from "react";
import { Link } from "react-router-dom";

import {
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
import { PageHeader } from "@/components/layout/PageHeader";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { formatDuration, formatRelative } from "@/lib/format-time";
import { cn } from "@/lib/utils";

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

const Panel = ({
  title,
  meta,
  children,
  className,
}: {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
}): JSX.Element => (
  <section className={cn("min-w-0 border-t border-border", className)}>
    <header className="flex h-control-comfortable items-center justify-between gap-3 border-b border-border/70 px-4">
      <h2 className="text-label font-medium text-foreground">{title}</h2>
      {meta ? <div className="text-micro text-muted-foreground">{meta}</div> : null}
    </header>
    <div className="min-w-0 p-4">{children}</div>
  </section>
);

/**
 * Workspace posture: the status mix of every attempt, once. The counts used to
 * be printed twice in this fold — as hero tiles and again as a bar — and the
 * tiles labelled execution counts as runs.
 */
const ExecutionStatus = ({ counts }: { counts: ExecutionRollup }): JSX.Element => (
  <div className="space-y-3">
    <StatusDistribution counts={counts} />
    <p className="font-mono text-micro tabular-nums text-muted-foreground">
      {counts.total} executions
    </p>
  </div>
);

const ACTIVITY_BUCKETS = 12;
const ACTIVITY_WINDOW_MS = 24 * 60 * 60 * 1000;

/**
 * Executions *touched* per two-hour bucket over the last day. The previous
 * version plotted run creation, which says nothing about whether the workspace
 * is busy — a swept experiment creates 200 runs in one second.
 */
const ActivityPlot = ({ rows }: { rows: WorkspaceRunRow[] }): JSX.Element => {
  const { points, peak } = useMemo(() => {
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
    const max = Math.max(1, ...values);
    return {
      peak: Math.max(...values),
      points: values.map((value, index) => ({
        x: (index / (values.length - 1)) * 100,
        y: 34 - (value / max) * 28,
      })),
    };
  }, [rows]);
  const line = points.map((point) => `${point.x},${point.y}`).join(" ");

  return (
    <div className="space-y-2">
      <svg
        viewBox="0 0 100 36"
        role="img"
        aria-label={`Execution starts and finishes per 2 hours over the last day; busiest bucket ${peak}`}
        className="h-24 w-full"
      >
        <polygon points={`0,36 ${line} 100,36`} className="fill-accent/15" />
        <polyline points={line} fill="none" className="stroke-accent/70" strokeWidth="1" />
      </svg>
      <div className="flex justify-between font-mono text-micro text-muted-foreground">
        <span>−24h</span>
        <span>−12h</span>
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
  const subtitle = `${rows.length} runs · ${counts.total} executions${
    activeWorkspace ? ` · ${activeWorkspace.label}` : ""
  }${lastSyncedAt ? ` · synced ${formatRelative(lastSyncedAt.toISOString())}` : ""}`;

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-background">
      <PageHeader
        icon={LayoutDashboard}
        title="Dashboard"
        actions={
          <WorkbenchIconAction label="Open runs" kind="primary" size="default" asChild>
            <Link to="/runs">
              <Play className="size-3.5" />
            </Link>
          </WorkbenchIconAction>
        }
      />
      <div className="border-b border-border px-4 py-2 text-micro text-muted-foreground">
        {subtitle}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
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
          <div className="mb-4 flex items-center gap-2 border-y border-status-warning/30 bg-status-warning-soft px-4 py-2 text-micro text-status-warning-foreground">
            <TriangleAlert className="size-icon-sm" />
            <span>Run inventory is truncated; open Runs to narrow the dataset.</span>
          </div>
        ) : null}

        {rows.length > 0 ? (
          <div className="min-w-0">
            <div className="grid min-w-0 lg:grid-cols-2">
              <Panel
                title="Execution status"
                meta={<Gauge className="size-icon-sm" />}
                className="lg:border-r"
              >
                <ExecutionStatus counts={counts} />
              </Panel>
              <Panel title="Activity" meta="Last 24 hours">
                <ActivityPlot rows={rows} />
              </Panel>
              <Panel title="Backends" className="lg:border-r">
                <div className="space-y-3">
                  <Backends rows={rows} />
                  <StatusLegend />
                </div>
              </Panel>
              <Panel title="Run duration" meta="Finished runs">
                <Histogram
                  values={durations}
                  format={formatDuration}
                  unit="runs"
                  ariaLabel="Distribution of wall-clock duration across finished runs"
                />
                {durations.length === 0 ? (
                  <p className="text-micro text-muted-foreground">No finished runs yet</p>
                ) : null}
              </Panel>
            </div>
            <Panel title="Schedule" meta="Most recently active">
              <Schedule
                items={scheduleItems(rows)}
                empty={
                  <p className="text-micro text-muted-foreground">
                    No run has started yet — nothing to place on a timeline.
                  </p>
                }
              />
            </Panel>
            <Panel title="Needs attention" meta="Failed runs">
              <NeedsAttention rows={rows} />
            </Panel>
          </div>
        ) : !loading && !error ? (
          <WorkbenchOperationState
            kind="empty"
            title="No runs yet"
            detail="Open a project or experiment to start tracked work."
          />
        ) : null}
      </div>
    </div>
  );
};
