// ─────────────────────────────────────────────────────────────────────────────
// Execution instruments shared by the workspace Dashboard and a project's
// Overview. Each takes the run rows of its scope and draws one shape; the page
// decides where it sits. Counts are execution counts — a run has N attempts —
// except the attention set, which is the runs whose latest attempt needs a person.
// ─────────────────────────────────────────────────────────────────────────────

import { ArrowDown, ArrowUp, BoxSelect } from "lucide-react";
import { type JSX, useCallback, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  ActivityChart,
  type BreakdownGroup,
  ChoiceToggle,
  DurationDots,
  type DurationPoint,
  type DurationSeries,
  formatSpan,
  StatusIcon,
  StatusTally,
  Tally,
  TimelineChart,
  type TimelineSpan,
  timeBuckets,
  type UnitMark,
} from "@/app/components/entity";
import { widgetEmptyCopy } from "@/app/dashboard/dashboardModel";
import { runPath } from "@/app/entities/paths";
import { formatScalar } from "@/app/renderers/dashboardData";
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

export interface ExecutionRollup {
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

const newestFirst = (left: WorkspaceRunRow, right: WorkspaceRunRow): number =>
  (timestamp(runActivityAt(right)) ?? 0) - (timestamp(runActivityAt(left)) ?? 0);

const runHref = (run: WorkspaceRunRow): string => runPath(run.projectId, run.experimentId, run.id);

const runKey = (run: WorkspaceRunRow): string => `${run.workspaceKey}:${run.id}`;

/**
 * The run page behind a chart mark. A mark's key is its run's key, or the run's
 * key plus an execution id (`ws:run:e02`), so one resolver serves every chart.
 */
export const runHrefForKey = (rows: readonly WorkspaceRunRow[], key: string): string | null => {
  const run = rows.find((item) => key === runKey(item) || key.startsWith(`${runKey(item)}:`));
  return run ? runHref(run) : null;
};

/** Navigate to the run a chart mark stands for. */
export const useOpenRun = (rows: readonly WorkspaceRunRow[]): ((key: string) => void) => {
  const navigate = useNavigate();
  return useCallback(
    (key: string) => {
      const href = runHrefForKey(rows, key);
      if (href) navigate(href);
    },
    [rows, navigate],
  );
};

export const EmptyLine = ({ children }: { children: string }): JSX.Element => (
  <p className="break-words text-label text-muted-foreground">{children}</p>
);

// ── Attention ────────────────────────────────────────────────────────────────

const ATTENTION: ReadonlySet<StatusGroupId> = new Set(["failed", "cancelled"]);

/** Runs whose latest attempt failed or was cancelled, newest first. */
export const attentionRuns = (rows: readonly WorkspaceRunRow[]): WorkspaceRunRow[] =>
  rows
    .filter((run) => {
      const group = groupForStatus(runPresentationStatus(run));
      return group !== null && ATTENTION.has(group);
    })
    .sort(newestFirst);

const ageOf = (at: string | null | undefined, now: number): string => {
  const ms = timestamp(at);
  return ms === null ? "" : formatSpan(Math.max(0, now - ms) / 1000);
};

/** Age of the newest and the oldest run needing a person: "16m → 6h ago". */
export const attentionEdges = (
  rows: readonly WorkspaceRunRow[],
  now = Date.now(),
): readonly [string, string] | undefined => {
  const flagged = attentionRuns(rows);
  const first = flagged[0];
  const last = flagged[flagged.length - 1];
  if (flagged.length < 2 || !first || !last) return undefined;
  const newest = ageOf(runActivityAt(first), now);
  const oldest = ageOf(runActivityAt(last), now);
  return newest && oldest ? [newest, `${oldest} ago`] : undefined;
};

/** One mark per run needing a person, newest first, each named with its age. */
export const attentionMarks = (rows: readonly WorkspaceRunRow[], now = Date.now()): UnitMark[] =>
  attentionRuns(rows).map((run) => {
    const group = groupForStatus(runPresentationStatus(run)) ?? "failed";
    const age = ageOf(runActivityAt(run), now);
    return {
      key: runKey(run),
      status: group,
      title: `${run.name || run.id} · ${group === "failed" ? "failed" : "cancelled"}${
        age ? ` ${age} ago` : ""
      }`,
    };
  });

/**
 * One mark per active execution. A running mark fills with its elapsed time
 * against twice the scope's median run, so the reference rule at half height
 * is "typical" and an overdue attempt stands above it. Queued marks are outlines.
 */
export const inFlightMarks = (
  rows: readonly WorkspaceRunRow[],
  medianSeconds: number | null,
  now = Date.now(),
): UnitMark[] => {
  const active = rows.flatMap((run) =>
    run.executions.flatMap((execution) => {
      const group = groupForStatus(execution.status);
      if (group !== "running" && group !== "pending") return [];
      const since = timestamp(group === "running" ? execution.startedAt : execution.createdAt);
      const elapsed = since === null ? null : Math.max(0, now - since) / 1000;
      return [{ run, execution, group, elapsed }];
    }),
  );
  const rank = (item: (typeof active)[number]): number =>
    (item.group === "running" ? 1e12 : 0) + (item.elapsed ?? 0);
  return [...active]
    .sort((left, right) => rank(right) - rank(left))
    .map(({ run, execution, group, elapsed }) => {
      const name = `${run.name || run.id} · ${execution.executionId}`;
      const age = elapsed === null ? "" : ` ${formatSpan(elapsed)}`;
      if (group === "pending") {
        return {
          key: `${runKey(run)}:${execution.executionId}`,
          status: "pending" as const,
          outline: true,
          title: `${name} · queued${age}`,
        };
      }
      return {
        key: `${runKey(run)}:${execution.executionId}`,
        status: "running" as const,
        title: `${name} · running${age}`,
        level:
          medianSeconds && medianSeconds > 0 && elapsed !== null
            ? elapsed / (2 * medianSeconds)
            : undefined,
      };
    });
};

export const NeedsAttention = ({
  rows,
  inventoryBlocked,
}: {
  rows: readonly WorkspaceRunRow[];
  inventoryBlocked: boolean;
}): JSX.Element => {
  const flagged = attentionRuns(rows);
  if (flagged.length === 0) {
    return <EmptyLine>{widgetEmptyCopy(inventoryBlocked, "No runs need attention.")}</EmptyLine>;
  }
  return (
    <ul className="divide-y divide-border/60 border-y border-border/60">
      {flagged.map((run) => {
        const group = groupForStatus(runPresentationStatus(run)) ?? "failed";
        const at = runActivityAt(run);
        const when = at && !Number.isNaN(Date.parse(at)) ? formatRelative(at) : "";
        return (
          <li key={runKey(run)}>
            <Link
              to={runHref(run)}
              className="grid grid-cols-[auto_minmax(0,1fr)_minmax(0,16rem)_auto] items-center gap-x-3 px-2 py-row-pad outline-none hover:bg-interactive focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-inset"
            >
              <StatusIcon status={group === "failed" ? "failed" : "cancelled"} />
              <span
                className="min-w-0 truncate text-body text-foreground"
                title={run.name || run.id}
              >
                {run.name || run.id}
              </span>
              <span
                className="min-w-0 truncate text-label text-muted-foreground"
                title={`${run.projectName} · ${run.experimentName}`}
              >
                {run.projectName} · {run.experimentName}
              </span>
              <span className="whitespace-nowrap font-mono text-micro tabular-nums text-muted-foreground">
                {when}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
};

// ── Activity ─────────────────────────────────────────────────────────────────

const ACTIVITY_WINDOW = {
  "24h": { ms: 24 * 60 * 60 * 1000, buckets: 24, tickEvery: 6, words: "24 hours" },
  "7d": { ms: 7 * 24 * 60 * 60 * 1000, buckets: 28, tickEvery: 4, words: "7 days" },
} as const;

type ActivityWindow = keyof typeof ACTIVITY_WINDOW;

const WINDOW_CHOICES = (Object.keys(ACTIVITY_WINDOW) as ActivityWindow[]).map((value) => ({
  value,
  label: value,
}));

export const ActivityPanel = ({
  rows,
  inventoryBlocked,
  selection,
  onSelect,
}: {
  rows: readonly WorkspaceRunRow[];
  inventoryBlocked: boolean;
  /** The brushed window the rest of the overview is filtered to. */
  selection: [number, number] | null;
  onSelect: (window: [number, number] | null) => void;
}): JSX.Element => {
  const [span, setSpan] = useState<ActivityWindow>("24h");
  const [now] = useState(() => Date.now());
  const spec = ACTIVITY_WINDOW[span];
  const buckets = useMemo(() => {
    const happenings = rows.flatMap((run) =>
      run.executions.map((execution) => ({
        startedAt: timestamp(execution.startedAt),
        finishedAt: timestamp(execution.finishedAt),
        outcome: groupForStatus(execution.status),
      })),
    );
    return timeBuckets(happenings, now, spec.ms, spec.buckets);
  }, [rows, spec, now]);
  const chartWindow = useMemo(() => ({ from: now - spec.ms, to: now }), [now, spec]);

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

  return (
    <section aria-label="Activity" className="min-w-0">
      <header className="flex min-w-0 flex-wrap items-center gap-x-5 gap-y-1 pb-3 text-label">
        <h2 className="font-medium text-foreground">Activity</h2>
        <Tally
          icon={ArrowUp}
          value={started}
          label={`${started} executions started — bars above the axis`}
          className="text-muted-foreground"
        />
        <Tally
          icon={ArrowDown}
          value={finished}
          label={`${finished} executions finished — bars below the axis, by outcome`}
          className="text-muted-foreground"
        />
        {failed > 0 ? <StatusTally status="failed" count={failed} unit="executions" /> : null}
        <span className="ml-auto flex items-center gap-3 text-muted-foreground">
          <span
            role="img"
            aria-label="Drag across the chart to filter the overview to that window"
            title="Drag across the chart to filter the overview to that window"
          >
            <BoxSelect aria-hidden className="size-icon-sm" />
          </span>
          <ChoiceToggle
            label="Activity window"
            choices={WINDOW_CHOICES}
            value={span}
            onChange={(next) => {
              setSpan(next);
              if (selection) onSelect(null);
            }}
          />
        </span>
      </header>
      {started + finished === 0 ? (
        <div className="flex h-36 items-center justify-center border-y border-dashed border-border">
          <EmptyLine>
            {widgetEmptyCopy(inventoryBlocked, `No execution activity in the last ${spec.words}.`)}
          </EmptyLine>
        </div>
      ) : (
        <ActivityChart key={span} buckets={buckets} window={chartWindow} onBrush={onSelect} />
      )}
    </section>
  );
};

// ── Timeline ─────────────────────────────────────────────────────────────────

const timelineSpans = (rows: readonly WorkspaceRunRow[], limit: number): TimelineSpan[] =>
  [...rows]
    .sort(newestFirst)
    .flatMap((run) => {
      const start = timestamp(runStartedAt(run));
      if (start === null) return [];
      const end = timestamp(runFinishedAt(run));
      const status = groupForStatus(runPresentationStatus(run));
      const active = status === "running" || status === "pending";
      const finish = active ? null : end;
      const word = STATUS_GROUPS.find((group) => group.id === status)?.label ?? "Unknown";
      const took = formatSpan(Math.max(0, (finish ?? Date.now()) - start) / 1000);
      return [
        {
          key: runKey(run),
          label: run.name || run.id,
          start,
          end: finish,
          status,
          tip: `${run.name || run.id} · ${run.experimentName} · ${word} · ${took}`,
        },
      ];
    })
    .slice(0, limit);

export const RunTimeline = ({
  rows,
  limit = 40,
  inventoryBlocked,
}: {
  rows: readonly WorkspaceRunRow[];
  limit?: number;
  inventoryBlocked: boolean;
}): JSX.Element => {
  const spans = useMemo(() => timelineSpans(rows, limit), [rows, limit]);
  const openRun = useOpenRun(rows);
  if (spans.length === 0) {
    return <EmptyLine>{widgetEmptyCopy(inventoryBlocked, "No run has started yet.")}</EmptyLine>;
  }
  return <TimelineChart spans={spans} onPick={openRun} />;
};

// ── Durations ────────────────────────────────────────────────────────────────

const FINISHED: ReadonlySet<StatusGroupId> = new Set(["succeeded", "failed", "cancelled"]);

/**
 * One point per finished run: its first start to its last finish. A run whose
 * latest attempt is still active is not finished, whatever an earlier attempt did.
 */
export const durationPointsOf = (rows: readonly WorkspaceRunRow[]): DurationPoint[] =>
  rows.flatMap((run) => {
    const status = groupForStatus(runPresentationStatus(run));
    if (status === null || !FINISHED.has(status)) return [];
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

/** What an Overview groups its scope by: projects, experiments, or one swept parameter's values. */
export type GroupKey = "project" | "experiment" | `param:${string}`;

export const paramGroup = (key: string): GroupKey => `param:${key}`;

/**
 * Parameters whose value differs between the rows, in first-seen order — the
 * axes a grouping can split on. A parameter every run shares is not an axis.
 */
export const varyingParameterKeys = (rows: readonly WorkspaceRunRow[]): string[] => {
  const values = new Map<string, Set<string>>();
  for (const run of rows) {
    for (const [key, value] of Object.entries(run.parameters ?? {})) {
      const seen = values.get(key) ?? new Set<string>();
      seen.add(formatScalar(value));
      values.set(key, seen);
    }
  }
  return [...values.entries()].filter(([, seen]) => seen.size > 1).map(([key]) => key);
};

const groupOf = (run: WorkspaceRunRow, key: GroupKey): { id: string; label: string } => {
  if (key === "project") return { id: run.projectId, label: run.projectName || run.projectId };
  if (key === "experiment") {
    return { id: run.experimentId, label: run.experimentName || run.experimentId };
  }
  const name = key.slice("param:".length);
  const label = `${name}=${formatScalar(run.parameters?.[name])}`;
  return { id: label, label };
};

const partition = (
  rows: readonly WorkspaceRunRow[],
  key: GroupKey,
): Array<{ id: string; label: string; rows: WorkspaceRunRow[] }> => {
  const groups = new Map<string, { id: string; label: string; rows: WorkspaceRunRow[] }>();
  for (const run of rows) {
    const { id, label } = groupOf(run, key);
    const existing = groups.get(id);
    groups.set(id, { id, label, rows: [...(existing?.rows ?? []), run] });
  }
  return [...groups.values()];
};

/** Finished-run durations per group, on one shared axis, so groups compare by position. */
export const durationSeriesBy = (
  rows: readonly WorkspaceRunRow[],
  key: GroupKey,
): DurationSeries[] =>
  partition(rows, key)
    .map((group) => ({ id: group.id, label: group.label, points: durationPointsOf(group.rows) }))
    .filter((series) => series.points.length > 0)
    .sort((left, right) => right.points.length - left.points.length);

export const DurationsBy = ({
  rows,
  groupBy,
}: {
  rows: readonly WorkspaceRunRow[];
  groupBy: GroupKey;
}): JSX.Element => {
  const series = useMemo(() => durationSeriesBy(rows, groupBy), [rows, groupBy]);
  const openRun = useOpenRun(rows);
  if (series.length === 0) return <EmptyLine>No finished runs yet.</EmptyLine>;
  return <DurationDots series={series} onPick={openRun} />;
};

// ── Breakdowns ───────────────────────────────────────────────────────────────

/** Execution status mix per project or experiment, busiest first. */
export const statusGroupsBy = (
  rows: readonly WorkspaceRunRow[],
  key: GroupKey,
  onSelect?: (id: string) => void,
): BreakdownGroup[] =>
  partition(rows, key)
    .map((group) => ({
      id: group.id,
      label: group.label,
      counts: rollupExecutions(group.rows),
      onSelect: onSelect ? () => onSelect(group.id) : undefined,
    }))
    .filter((group) => group.counts.total > 0)
    .sort((left, right) => right.counts.total - left.counts.total);

export const backendGroups = (rows: readonly WorkspaceRunRow[], limit = 6): BreakdownGroup[] => {
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
