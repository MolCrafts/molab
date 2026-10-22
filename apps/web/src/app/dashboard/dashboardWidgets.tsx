import { type JSX, type ReactNode, useMemo } from "react";
import { Link } from "react-router-dom";

import {
  type DurationPoint,
  DurationStrip,
  EventColumns,
  EventLegend,
  Figure,
  formatSpan,
  quantile,
  Schedule,
  type ScheduleItem,
  STATUS_FILL,
  StatusBreakdown,
  StatusLedger,
  timeBuckets,
} from "@/app/components/entity";
import { widgetEmptyCopy } from "@/app/dashboard/dashboardModel";
import type { DashboardWidget } from "@/app/dashboard/layout";
import { runPath } from "@/app/entities/paths";
import {
  runActivityAt,
  runExecutorFacet,
  runFinishedAt,
  runPresentationStatus,
  runStartedAt,
} from "@/app/runs/projections";
import { groupForStatus, STATUS_GROUPS, type StatusGroupId } from "@/app/runs/statusGroups";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { formatRelative } from "@/lib/format-time";

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
export const rollupExecutions = (rows: readonly WorkspaceRunRow[]): ExecutionRollup => {
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

const runHref = (run: WorkspaceRunRow): string => runPath(run.projectId, run.experimentId, run.id);

const runKey = (run: WorkspaceRunRow): string => `${run.workspaceKey}:${run.id}`;

const EmptyLine = ({ children }: { children: string }): JSX.Element => (
  <p className="break-words text-label text-muted-foreground">{children}</p>
);

/** The sentence a widget body opens with: its numbers, then an optional key. */
const Readout = ({ children, aside }: { children: ReactNode; aside?: ReactNode }): JSX.Element => (
  <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pb-3 text-label text-muted-foreground">
    <p className="min-w-0">{children}</p>
    {aside != null ? <p className="min-w-0">{aside}</p> : null}
  </div>
);

const ACTIVITY_WINDOW = {
  "24h": { ms: 24 * 60 * 60 * 1000, buckets: 24, tickEvery: 6, words: "24 hours" },
  "7d": { ms: 7 * 24 * 60 * 60 * 1000, buckets: 28, tickEvery: 4, words: "7 days" },
} as const;

const ActivityGauge = ({
  rows,
  window: span,
  events,
  inventoryBlocked,
}: {
  rows: WorkspaceRunRow[];
  window: "24h" | "7d";
  events: "starts" | "finishes" | "both";
  inventoryBlocked: boolean;
}): JSX.Element => {
  const spec = ACTIVITY_WINDOW[span];
  const buckets = useMemo(() => {
    const happenings = rows.flatMap((run) =>
      run.executions.map((execution) => ({
        startedAt: timestamp(execution.startedAt),
        finishedAt: timestamp(execution.finishedAt),
        outcome: groupForStatus(execution.status),
      })),
    );
    return timeBuckets(happenings, Date.now(), spec.ms, spec.buckets);
  }, [rows, spec]);

  const showStarts = events !== "finishes";
  const showFinishes = events !== "starts";
  const started = buckets.reduce((sum, bucket) => sum + bucket.starts, 0);
  const finished = buckets.reduce(
    (sum, bucket) =>
      sum +
      bucket.finishes.succeeded +
      bucket.finishes.failed +
      bucket.finishes.cancelled +
      bucket.finishes.other,
    0,
  );
  const failed = buckets.reduce((sum, bucket) => sum + bucket.finishes.failed, 0);
  if ((showStarts ? started : 0) + (showFinishes ? finished : 0) === 0) {
    return (
      <EmptyLine>
        {widgetEmptyCopy(inventoryBlocked, `No execution activity in the last ${spec.words}.`)}
      </EmptyLine>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Readout aside={<EventLegend showStarts={showStarts} showFinishes={showFinishes} />}>
        {showStarts ? (
          <>
            <Figure>{started}</Figure> started
          </>
        ) : null}
        {showStarts && showFinishes ? " · " : null}
        {showFinishes ? (
          <>
            <Figure>{finished}</Figure> finished
            {failed > 0 ? (
              <>
                {", "}
                <Figure className="text-status-failed-foreground">{failed}</Figure> failed
              </>
            ) : null}
          </>
        ) : null}
        {` in ${spec.words}`}
      </Readout>
      <EventColumns
        buckets={buckets}
        windowMs={spec.ms}
        showStarts={showStarts}
        showFinishes={showFinishes}
        tickEvery={spec.tickEvery}
        className="min-h-0 flex-1"
      />
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
      id: runKey(run),
      label: run.name || run.id,
      detail: run.experimentName,
      start: timestamp(runStartedAt(run)),
      end: timestamp(runFinishedAt(run)),
      status: groupForStatus(runPresentationStatus(run)),
      render: (children: ReactNode) => (
        <Link
          to={runHref(run)}
          className="block min-w-0 outline-none hover:bg-interactive focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-inset"
        >
          {children}
        </Link>
      ),
    }));

const durationPointsOf = (
  rows: readonly WorkspaceRunRow[],
  succeededOnly: boolean,
): DurationPoint[] =>
  rows.flatMap((run) => {
    const status = groupForStatus(runPresentationStatus(run));
    if (succeededOnly && status !== "succeeded") return [];
    const start = timestamp(runStartedAt(run));
    const end = timestamp(runFinishedAt(run));
    if (start === null || end === null || end < start) return [];
    return [
      {
        id: runKey(run),
        seconds: (end - start) / 1000,
        status,
        label: `${run.name || run.id} · ${run.experimentName}`,
        href: runHref(run),
      },
    ];
  });

const backendGroups = (rows: readonly WorkspaceRunRow[], limit: number) => {
  const byBackend = new Map<string, WorkspaceRunRow[]>();
  for (const run of rows) {
    const named = runExecutorFacet(run, "backend");
    // A run that never started has no executor. Calling it "unassigned"
    // draws a zero bar beside a legend and looks like a broken chart.
    const backends =
      named.length > 0 ? named : rollupExecutions([run]).total > 0 ? ["unassigned"] : [];
    for (const backend of backends) {
      byBackend.set(backend, [...(byBackend.get(backend) ?? []), run]);
    }
  }
  return [...byBackend.entries()]
    .map(([backend, backendRuns]) => ({
      id: backend,
      label: backend,
      counts: rollupExecutions(backendRuns),
    }))
    .filter((group) => group.counts.total > 0)
    .sort((left, right) => right.counts.total - left.counts.total)
    .slice(0, limit);
};

const NeedsAttention = ({
  rows,
  statuses,
  limit,
  inventoryBlocked,
}: {
  rows: WorkspaceRunRow[];
  statuses: readonly ("failed" | "cancelled")[];
  limit: number;
  inventoryBlocked: boolean;
}): JSX.Element => {
  const wanted = new Set<StatusGroupId>(statuses);
  const flagged = rows
    .filter((run) => {
      const group = groupForStatus(runPresentationStatus(run));
      return group !== null && wanted.has(group);
    })
    .sort(
      (left, right) =>
        (timestamp(runActivityAt(right)) ?? 0) - (timestamp(runActivityAt(left)) ?? 0),
    )
    .slice(0, limit);

  if (flagged.length === 0) {
    return <EmptyLine>{widgetEmptyCopy(inventoryBlocked, "No runs need attention.")}</EmptyLine>;
  }
  return (
    <ul className="space-y-1">
      {flagged.map((run) => {
        const group = groupForStatus(runPresentationStatus(run)) ?? "failed";
        const at = runActivityAt(run);
        const when = at && !Number.isNaN(Date.parse(at)) ? formatRelative(at) : "";
        return (
          <li key={runKey(run)}>
            <Link
              to={runHref(run)}
              className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-baseline gap-x-2 rounded-control py-1 outline-none hover:bg-interactive focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-inset"
            >
              <span
                role="img"
                aria-label={group === "failed" ? "Failed" : "Cancelled"}
                className={`size-2 rounded-full ${STATUS_FILL[group]}`}
              />
              <span
                className="min-w-0 truncate text-body text-foreground"
                title={run.name || run.id}
              >
                {run.name || run.id}
              </span>
              <span className="whitespace-nowrap font-mono text-micro tabular-nums text-muted-foreground">
                {when}
              </span>
              <span />
              <span
                className="col-span-2 min-w-0 truncate text-label text-muted-foreground"
                title={run.experimentName}
              >
                {run.experimentName}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
};

export const DashboardWidgetBody = ({
  widget,
  rows,
  inventoryBlocked = false,
}: {
  widget: DashboardWidget;
  rows: WorkspaceRunRow[];
  /** When set, an empty widget must not claim the lab is quiet. */
  inventoryBlocked?: boolean;
}): JSX.Element => {
  if (widget.kind === "execution-status") {
    const all = rollupExecutions(rows);
    if (all.total === 0) {
      return <EmptyLine>{widgetEmptyCopy(inventoryBlocked, "No executions yet.")}</EmptyLine>;
    }
    const shown = new Set<StatusGroupId>(widget.options.statuses);
    const counts = emptyRollup();
    for (const group of STATUS_GROUPS) {
      if (!shown.has(group.id)) continue;
      counts[group.id] = all[group.id];
      counts.total += all[group.id];
    }
    return <StatusLedger counts={counts} unit={["execution", "executions"]} />;
  }

  if (widget.kind === "activity") {
    return (
      <ActivityGauge
        rows={rows}
        window={widget.options.window}
        events={widget.options.events}
        inventoryBlocked={inventoryBlocked}
      />
    );
  }

  if (widget.kind === "backends") {
    const groups = backendGroups(rows, widget.options.limit);
    if (groups.length === 0) {
      return (
        <EmptyLine>{widgetEmptyCopy(inventoryBlocked, "No executor recorded yet.")}</EmptyLine>
      );
    }
    return <StatusBreakdown groups={groups} />;
  }

  if (widget.kind === "run-duration") {
    const points = durationPointsOf(rows, widget.options.scope === "succeeded");
    if (points.length === 0) {
      return <EmptyLine>{widgetEmptyCopy(inventoryBlocked, "No finished runs yet.")}</EmptyLine>;
    }
    const sorted = points.map((point) => point.seconds).sort((left, right) => left - right);
    return (
      <div className="min-w-0">
        <Readout>
          median <Figure>{formatSpan(quantile(sorted, 0.5))}</Figure> across{" "}
          <Figure>{points.length}</Figure> {points.length === 1 ? "run" : "runs"}
        </Readout>
        <DurationStrip series={[{ id: "all", points }]} />
      </div>
    );
  }

  if (widget.kind === "schedule") {
    return (
      <Schedule
        items={scheduleItems(rows, widget.options.limit)}
        empty={
          <EmptyLine>{widgetEmptyCopy(inventoryBlocked, "No run has started yet.")}</EmptyLine>
        }
      />
    );
  }

  return (
    <NeedsAttention
      rows={rows}
      statuses={widget.options.statuses}
      limit={widget.options.limit}
      inventoryBlocked={inventoryBlocked}
    />
  );
};
