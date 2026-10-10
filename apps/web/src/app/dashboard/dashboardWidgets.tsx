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
import type { DashboardWidget } from "@/app/dashboard/layout";
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
import { formatDuration, formatRelative } from "@/lib/format-time";

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

/** Every count on this page is an execution count — a run has N attempts. */
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

const runDurationSeconds = (run: WorkspaceRunRow): number | null => {
  const start = timestamp(runStartedAt(run));
  const end = timestamp(runFinishedAt(run));
  if (start === null || end === null || end < start) return null;
  return (end - start) / 1000;
};

const ActivityPlot = ({
  rows,
  window: span,
  events,
}: {
  rows: WorkspaceRunRow[];
  window: "24h" | "7d";
  events: "starts" | "finishes" | "both";
}): JSX.Element => {
  const { bars, peak, label } = useMemo(() => {
    const now = Date.now();
    const buckets = span === "24h" ? 12 : 7;
    const width = ((span === "24h" ? 24 : 7 * 24) * 60 * 60 * 1000) / buckets;
    const values = new Array<number>(buckets).fill(0);
    for (const run of rows) {
      for (const execution of run.executions) {
        const instants = [
          events === "finishes" ? null : execution.startedAt,
          events === "starts" ? null : execution.finishedAt,
        ];
        for (const instant of instants) {
          const at = timestamp(instant);
          if (at === null) continue;
          const index = buckets - 1 - Math.floor((now - at) / width);
          if (index >= 0 && index < values.length) values[index] += 1;
        }
      }
    }
    return {
      peak: Math.max(...values),
      label: span === "24h" ? "−24h" : "−7d",
      bars: values.map((value, index) => ({
        id: `b${index - (buckets - 1)}`,
        value,
      })),
    };
  }, [rows, span, events]);

  if (peak === 0) {
    return (
      <p className="text-micro text-muted-foreground">
        No execution activity in the last {span === "24h" ? "24 hours" : "7 days"}
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div
        role="img"
        aria-label={`Execution events over the last ${span}; busiest bucket ${peak}`}
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
        <span>{label}</span>
        <span>peak {peak}</span>
        <span>now</span>
      </div>
    </div>
  );
};

const scheduleItems = (rows: WorkspaceRunRow[], limit: number): ScheduleItem[] =>
  [...rows]
    .sort(
      (left, right) =>
        (timestamp(runActivityAt(right)) ?? 0) - (timestamp(runActivityAt(left)) ?? 0),
    )
    .slice(0, limit)
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

export const DashboardWidgetBody = ({
  widget,
  rows,
}: {
  widget: DashboardWidget;
  rows: WorkspaceRunRow[];
}): JSX.Element => {
  if (widget.kind === "execution-status") {
    const counts = rollupExecutions(rows);
    return counts.total === 0 ? (
      <p className="text-micro text-muted-foreground">No executions yet</p>
    ) : (
      <StatusDistribution counts={counts} groups={widget.options.statuses} unit="executions" />
    );
  }

  if (widget.kind === "activity") {
    return (
      <ActivityPlot rows={rows} window={widget.options.window} events={widget.options.events} />
    );
  }

  if (widget.kind === "backends") {
    const groups = (() => {
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
        .slice(0, widget.options.limit);
    })();
    if (groups.length === 0) {
      return <p className="text-micro text-muted-foreground">No executor recorded yet</p>;
    }
    return (
      <>
        <StatusBreakdown groups={groups} />
        <StatusLegend className="mt-3" />
      </>
    );
  }

  if (widget.kind === "run-duration") {
    const durations = rows
      .filter(
        (run) =>
          widget.options.scope === "finished" ||
          groupForStatus(runPresentationStatus(run)) === "succeeded",
      )
      .map(runDurationSeconds)
      .filter((value): value is number => value !== null);
    if (durations.length === 0) {
      return <p className="text-micro text-muted-foreground">No finished runs yet</p>;
    }
    return (
      <Histogram
        values={durations}
        format={formatDuration}
        unit="runs"
        ariaLabel="Distribution of wall-clock duration across finished runs"
      />
    );
  }

  if (widget.kind === "schedule") {
    return (
      <Schedule
        items={scheduleItems(rows, widget.options.limit)}
        empty={<p className="text-micro text-muted-foreground">No run has started yet.</p>}
      />
    );
  }

  const statuses = new Set(widget.options.statuses);
  const flagged = rows
    .filter((run) => {
      const group = groupForStatus(runPresentationStatus(run));
      return group === "failed" || group === "cancelled" ? statuses.has(group) : false;
    })
    .sort(
      (left, right) =>
        (timestamp(runActivityAt(right)) ?? 0) - (timestamp(runActivityAt(left)) ?? 0),
    )
    .slice(0, widget.options.limit);

  if (flagged.length === 0) {
    return <p className="text-micro text-muted-foreground">No runs need attention</p>;
  }
  return (
    <ul className="divide-y divide-border/50">
      {flagged.map((run) => {
        const group = groupForStatus(runPresentationStatus(run));
        const failed = group === "failed";
        return (
          <li key={run.id}>
            <Link
              to={runPath(run.projectId, run.experimentId, run.id)}
              className="flex min-w-0 items-center gap-2 py-row-pad hover:bg-interactive"
            >
              <span
                aria-hidden
                className={
                  failed
                    ? "size-1.5 shrink-0 rounded-full bg-status-failed"
                    : "size-1.5 shrink-0 rounded-full bg-status-cancelled"
                }
              />
              <span
                className={
                  failed
                    ? "min-w-0 flex-1 truncate text-micro text-status-failed-foreground"
                    : "min-w-0 flex-1 truncate text-micro text-muted-foreground"
                }
              >
                {run.name || run.id}
              </span>
              <span
                className={
                  failed
                    ? "shrink-0 text-micro text-status-failed-foreground"
                    : "shrink-0 text-micro text-muted-foreground"
                }
              >
                {failed ? "Failed" : "Cancelled"}
              </span>
              <span className="shrink-0 font-mono text-micro text-muted-foreground">
                {formatRelative(runActivityAt(run))}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
};
