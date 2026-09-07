import { Activity, Gauge, LayoutDashboard, Play, TriangleAlert } from "lucide-react";
import { type JSX, type ReactNode, useMemo } from "react";
import { Link } from "react-router-dom";

import { runPath } from "@/app/entities/paths";
import {
  runActivityAt,
  runExecutorFacet,
  runFinishedAt,
  runPresentationStatus,
} from "@/app/runs/projections";
import { groupForStatus, STATUS_GROUPS } from "@/app/runs/statusGroups";
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

const timestamp = (value: string | null | undefined): number => {
  const parsed = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : Number.NaN;
};

const startedAt = (run: WorkspaceRunRow): number => {
  const starts = run.executions
    .map((execution) => timestamp(execution.startedAt))
    .filter(Number.isFinite);
  return starts.length > 0 ? Math.min(...starts) : timestamp(run.createdAt);
};

const activityAt = (run: WorkspaceRunRow): number => {
  return timestamp(runActivityAt(run));
};

const averageWaitSeconds = (rows: WorkspaceRunRow[]): number | null => {
  const waits = rows
    .flatMap((run) =>
      run.executions.map((execution) => {
        const created = timestamp(execution.createdAt);
        const started = timestamp(execution.startedAt);
        return Number.isFinite(created) && Number.isFinite(started) && started >= created
          ? (started - created) / 1000
          : null;
      }),
    )
    .filter((value): value is number => value !== null);
  return waits.length > 0 ? waits.reduce((sum, value) => sum + value, 0) / waits.length : null;
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
    <header className="flex h-9 items-center justify-between gap-3 border-b border-border/70 px-3">
      <h2 className="text-label font-medium text-foreground">{title}</h2>
      {meta ? <div className="text-micro text-muted-foreground">{meta}</div> : null}
    </header>
    <div className="min-w-0 p-3">{children}</div>
  </section>
);

const Summary = ({ rows }: { rows: WorkspaceRunRow[] }): JSX.Element => {
  const counts = useMemo(() => {
    const next = { running: 0, pending: 0, failed: 0, succeeded: 0 };
    for (const run of rows) {
      for (const execution of run.executions) {
        const group = groupForStatus(execution.status);
        if (group && group !== "cancelled") next[group] += 1;
      }
    }
    return next;
  }, [rows]);
  const items = [
    { label: "Running", value: counts.running, tone: "text-status-running-foreground" },
    { label: "Queued", value: counts.pending, tone: "text-muted-foreground" },
    { label: "Failed", value: counts.failed, tone: "text-status-failed-foreground" },
    { label: "Succeeded", value: counts.succeeded, tone: "text-status-completed-foreground" },
    {
      label: "Average wait",
      value: formatDuration(averageWaitSeconds(rows)),
      tone: "text-foreground",
    },
  ];

  return (
    <section aria-labelledby="dashboard-summary" className="border-y border-border">
      <header className="flex h-9 items-center justify-between px-3">
        <div>
          <h2 id="dashboard-summary" className="text-label font-medium text-foreground">
            Execution summary
          </h2>
          <p className="text-micro text-muted-foreground">Current workspace</p>
        </div>
        <span className="text-micro text-muted-foreground">{rows.length} runs</span>
      </header>
      <dl className="grid grid-cols-2 border-t border-border/70 sm:grid-cols-5">
        {items.map((item) => (
          <div
            key={item.label}
            className="border-b border-border/70 px-3 py-2 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0"
          >
            <dd className={cn("font-mono text-body-lg font-semibold tabular-nums", item.tone)}>
              {item.value}
            </dd>
            <dt className="mt-0.5 text-micro text-muted-foreground">{item.label}</dt>
          </div>
        ))}
      </dl>
    </section>
  );
};

const StatusMix = ({ rows }: { rows: WorkspaceRunRow[] }): JSX.Element => (
  <div className="space-y-2">
    {STATUS_GROUPS.map((spec) => {
      const executions = rows.flatMap((run) => run.executions);
      const count = executions.filter(
        (execution) => groupForStatus(execution.status) === spec.id,
      ).length;
      const ratio = executions.length > 0 ? count / executions.length : 0;
      return (
        <div
          key={spec.id}
          className="grid grid-cols-[5rem_minmax(0,1fr)_2.25rem] items-center gap-2"
        >
          <span className="flex items-center gap-2 text-micro text-muted-foreground">
            <span className="size-1.5 rounded-full" style={{ backgroundColor: spec.color }} />
            {spec.label}
          </span>
          <span className="h-1 overflow-hidden rounded-full bg-muted">
            <span
              className="block h-full rounded-full"
              style={{ width: `${Math.max(2, ratio * 100)}%`, backgroundColor: spec.color }}
            />
          </span>
          <span className="text-right font-mono text-micro tabular-nums text-foreground">
            {count}
          </span>
        </div>
      );
    })}
  </div>
);

const ActivityPlot = ({ rows }: { rows: WorkspaceRunRow[] }): JSX.Element => {
  const points = useMemo(() => {
    const now = Date.now();
    const values = new Array<number>(9).fill(0);
    for (const run of rows) {
      const created = timestamp(run.createdAt);
      if (!Number.isFinite(created)) continue;
      const index = 8 - Math.floor((now - created) / (3 * 60 * 60 * 1000));
      if (index >= 0 && index < values.length) values[index] += 1;
    }
    const max = Math.max(1, ...values);
    return values.map((value, index) => ({
      x: (index / (values.length - 1)) * 100,
      y: 34 - (value / max) * 28,
    }));
  }, [rows]);
  const line = points.map((point) => `${point.x},${point.y}`).join(" ");

  return (
    <div className="space-y-2">
      <svg
        viewBox="0 0 100 36"
        role="img"
        aria-label="Runs created during the last 24 hours"
        className="h-24 w-full"
      >
        <polygon points={`0,36 ${line} 100,36`} className="fill-muted" />
        <polyline points={line} fill="none" className="stroke-muted-foreground" strokeWidth="1" />
        {points.map((point) => (
          <circle
            key={`${point.x}-${point.y}`}
            cx={point.x}
            cy={point.y}
            r="0.8"
            className="fill-status-completed"
          />
        ))}
      </svg>
      <div className="flex justify-between font-mono text-micro text-muted-foreground">
        <span>−24h</span>
        <span>−12h</span>
        <span>now</span>
      </div>
    </div>
  );
};

const BackendsAndFailures = ({ rows }: { rows: WorkspaceRunRow[] }): JSX.Element => {
  const backends = useMemo(() => {
    const counts = new Map<string, number>();
    for (const run of rows) {
      for (const backend of runExecutorFacet(run, "backend")) {
        counts.set(backend, (counts.get(backend) ?? 0) + 1);
      }
    }
    if (counts.size === 0) counts.set("Unassigned", 0);
    return [...counts.entries()].sort((left, right) => right[1] - left[1]).slice(0, 4);
  }, [rows]);
  const failures = rows
    .filter((run) => groupForStatus(runPresentationStatus(run)) === "failed")
    .slice(0, 3);
  const maxBackend = Math.max(1, ...backends.map(([, count]) => count));

  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <div className="space-y-2">
        <h3 className="text-micro font-medium uppercase tracking-wide text-muted-foreground">
          Backends
        </h3>
        {backends.map(([backend, count]) => (
          <div
            key={backend}
            className="grid grid-cols-[4.5rem_minmax(0,1fr)_2rem] items-center gap-2 text-micro"
          >
            <span className="truncate text-muted-foreground">{backend}</span>
            <span className="h-1 rounded-full bg-muted">
              <span
                className="block h-full rounded-full bg-status-completed"
                style={{ width: `${(count / maxBackend) * 100}%` }}
              />
            </span>
            <span className="text-right font-mono tabular-nums">{count}</span>
          </div>
        ))}
      </div>
      <div className="space-y-2">
        <h3 className="text-micro font-medium uppercase tracking-wide text-muted-foreground">
          Failures
        </h3>
        {failures.length > 0 ? (
          failures.map((run) => (
            <Link
              key={run.id}
              to={runPath(run.projectId, run.experimentId, run.id)}
              className="block truncate text-micro text-status-failed-foreground hover:underline"
            >
              {run.name || run.id}
            </Link>
          ))
        ) : (
          <p className="text-micro text-muted-foreground">No recent failures</p>
        )}
      </div>
    </div>
  );
};

const RecentActivity = ({ rows }: { rows: WorkspaceRunRow[] }): JSX.Element => {
  const recent = [...rows].sort((left, right) => activityAt(right) - activityAt(left)).slice(0, 5);
  return (
    <ol className="divide-y divide-border/60">
      {recent.map((run) => {
        const group = groupForStatus(runPresentationStatus(run));
        return (
          <li key={run.id}>
            <Link
              to={runPath(run.projectId, run.experimentId, run.id)}
              className="flex min-w-0 items-center gap-2 py-2 hover:bg-interactive"
            >
              <span
                className={cn(
                  "size-1.5 shrink-0 rounded-full",
                  group === "failed"
                    ? "bg-status-failed"
                    : group === "running"
                      ? "bg-status-running"
                      : "bg-status-completed",
                )}
              />
              <span className="min-w-0 flex-1 truncate text-micro text-foreground">
                {run.name || run.id}
              </span>
              <span className="shrink-0 text-micro text-muted-foreground">
                {formatRelative(runActivityAt(run))}
              </span>
            </Link>
          </li>
        );
      })}
    </ol>
  );
};

const Timeline = ({ rows }: { rows: WorkspaceRunRow[] }): JSX.Element => {
  const visible = rows.slice(0, 7);
  const starts = visible.map(startedAt).filter(Number.isFinite);
  const ends = visible
    .map((run) => {
      const finished = timestamp(runFinishedAt(run));
      return Number.isFinite(finished) ? finished : Date.now();
    })
    .filter(Number.isFinite);
  const min = starts.length > 0 ? Math.min(...starts) : 0;
  const max = ends.length > 0 ? Math.max(...ends) : min + 1;
  const span = Math.max(1, max - min);

  return (
    <div className="divide-y divide-border/60 border-y border-border/70">
      {visible.map((run) => {
        const start = startedAt(run);
        const finished = timestamp(runFinishedAt(run));
        const end = Number.isFinite(finished) ? finished : Date.now();
        const left = Number.isFinite(start) ? ((start - min) / span) * 100 : 0;
        const width = Number.isFinite(start)
          ? Math.max(1.5, ((Math.max(start, end) - start) / span) * 100)
          : 1.5;
        const group = groupForStatus(runPresentationStatus(run));
        return (
          <Link
            key={run.id}
            to={runPath(run.projectId, run.experimentId, run.id)}
            className="grid min-w-0 grid-cols-[10rem_minmax(0,1fr)] items-center gap-3 px-2 py-2 hover:bg-interactive"
          >
            <span className="min-w-0">
              <span className="block truncate text-micro font-medium text-foreground">
                {run.name || run.id}
              </span>
              <span className="block truncate text-micro text-muted-foreground">
                {run.experimentName}
              </span>
            </span>
            <span className="relative h-4 border-x border-border/60">
              <span
                className={cn(
                  "absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full",
                  group === "failed"
                    ? "bg-status-failed"
                    : group === "running"
                      ? "bg-status-running"
                      : group === "pending"
                        ? "bg-status-queued"
                        : "bg-status-completed",
                )}
                style={{ left: `${left}%`, width: `${Math.min(100 - left, width)}%` }}
              />
            </span>
          </Link>
        );
      })}
    </div>
  );
};

export const DashboardPage = ({ snapshot }: DashboardPageProps): JSX.Element => {
  const { rows, loading, error, lastSyncedAt, refresh, truncated } = useWorkspaceRuns();
  const activeWorkspace =
    snapshot.workspaces.find((workspace) => workspace.active) ?? snapshot.workspaces[0];
  const subtitle = `${rows.length} runs${activeWorkspace ? ` · ${activeWorkspace.label}` : ""}${
    lastSyncedAt ? ` · synced ${formatRelative(lastSyncedAt.toISOString())}` : ""
  }`;

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-background">
      <PageHeader
        icon={LayoutDashboard}
        title="Dashboard"
        titleTooltip={subtitle}
        actions={
          <WorkbenchIconAction label="Open runs" kind="primary" size="default" asChild>
            <Link to="/runs">
              <Play className="size-3.5" />
            </Link>
          </WorkbenchIconAction>
        }
      />
      <div className="border-b border-border px-3 pb-2 text-micro text-muted-foreground">
        {subtitle}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
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
          <div className="mb-3 flex items-center gap-2 border-y border-status-warning/30 bg-status-warning-soft px-3 py-2 text-micro text-status-warning-foreground">
            <TriangleAlert className="size-3.5" />
            <span>Run inventory is truncated; open Runs to narrow the dataset.</span>
          </div>
        ) : null}

        {rows.length > 0 ? (
          <div className="min-w-0">
            <Summary rows={rows} />
            <div className="grid min-w-0 lg:grid-cols-2">
              <Panel
                title="Status mix"
                meta={<Gauge className="size-3.5" />}
                className="lg:border-r"
              >
                <StatusMix rows={rows} />
              </Panel>
              <Panel title="Run activity" meta="Last 24 hours">
                <ActivityPlot rows={rows} />
              </Panel>
              <Panel title="Backends & failures" className="lg:border-r">
                <BackendsAndFailures rows={rows} />
              </Panel>
              <Panel title="Recent activity" meta={<Activity className="size-3.5" />}>
                <RecentActivity rows={rows} />
              </Panel>
            </div>
            <Panel title="Timeline" meta="Recent runs">
              <Timeline rows={rows} />
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
