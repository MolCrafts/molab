// ─────────────────────────────────────────────────────────────────────────────
// Execution instruments shared by the workspace Dashboard and a project's
// Overview. Each takes the run rows of its scope and draws one shape; the page
// decides where it sits. Counts are execution counts — a run has N attempts —
// except the attention set, which is the runs whose latest attempt needs a person.
// ─────────────────────────────────────────────────────────────────────────────

import { type JSX, useCallback, useMemo, useState } from "react";

import {
  ActivityChart,
  type BreakdownGroup,
  ChoiceToggle,
  DurationDots,
  type DurationPoint,
  type DurationSeries,
  formatSpan,
  timeBuckets,
  type UnitMark,
} from "@/app/components/entity";
import { widgetEmptyCopy } from "@/app/dashboard/dashboardModel";
import { runPath } from "@/app/entities/paths";
import { usePreview } from "@/app/preview/PreviewContext";
import { formatScalar } from "@/app/renderers/dashboardData";
import {
  runActivityAt,
  runExecutorFacet,
  runFinishedAt,
  runPresentationStatus,
  runStartedAt,
} from "@/app/runs/projections";
import { runLabel } from "@/app/runs/runTitle";
import type { WorkspaceRunRow } from "@/app/runs/types";
import {
  chartGroupOf,
  countStatuses,
  FINISHED_GROUPS,
  needsAttention,
  type StatusCounts,
} from "@/app/status/vocabulary";
import { parseInstant } from "@/lib/format-time";

/** Every count on this page is an execution count — a run has N attempts. */
export const rollupExecutions = (rows: readonly WorkspaceRunRow[]): StatusCounts =>
  countStatuses(rows.flatMap((run) => run.executions.map((execution) => execution.status)));

const newestFirst = (left: WorkspaceRunRow, right: WorkspaceRunRow): number =>
  (parseInstant(runActivityAt(right)) ?? 0) - (parseInstant(runActivityAt(left)) ?? 0);

const runHref = (run: WorkspaceRunRow): string => runPath(run.projectId, run.experimentId, run.id);

const runKey = (run: WorkspaceRunRow): string => `${run.workspaceKey}:${run.id}`;

/**
 * The run behind a chart mark. A mark's key is its run's key, or the run's key
 * plus an execution id (`ws:run:e02`), so one resolver serves every chart.
 */
export const runForKey = (
  rows: readonly WorkspaceRunRow[],
  key: string,
): WorkspaceRunRow | undefined =>
  rows.find((item) => key === runKey(item) || key.startsWith(`${runKey(item)}:`));

/** Preview the run a chart mark stands for (L12); ↵ / ↗ in the Preview opens it. */
export const useOpenRun = (rows: readonly WorkspaceRunRow[]): ((key: string) => void) => {
  const { preview } = usePreview();
  return useCallback(
    (key: string) => {
      const run = runForKey(rows, key);
      if (!run) return;
      // `ws:run:e02` is a mark for one attempt; `ws:run` for the run.
      const executionId = key.slice(`${runKey(run)}:`.length);
      if (key !== runKey(run) && executionId) {
        preview({
          kind: "attempt",
          runId: run.id,
          projectId: run.projectId,
          experimentId: run.experimentId,
          workspaceKey: run.workspaceKey,
          executionId,
        });
        return;
      }
      preview({
        kind: "run",
        runId: run.id,
        projectId: run.projectId,
        experimentId: run.experimentId,
        workspaceKey: run.workspaceKey,
        label: runLabel(run),
      });
    },
    [rows, preview],
  );
};

export const EmptyLine = ({ children }: { children: string }): JSX.Element => (
  <p className="break-words text-label text-muted-foreground">{children}</p>
);

// ── Attention ────────────────────────────────────────────────────────────────

/** Runs whose latest attempt failed or was interrupted, newest first. */
export const attentionRuns = (rows: readonly WorkspaceRunRow[]): WorkspaceRunRow[] =>
  rows.filter((run) => needsAttention(runPresentationStatus(run))).sort(newestFirst);

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
      const group = chartGroupOf(execution.status);
      if (group !== "running" && group !== "queued") return [];
      const since = parseInstant(group === "running" ? execution.startedAt : execution.createdAt);
      const elapsed = since === null ? null : Math.max(0, now - since) / 1000;
      return [{ run, execution, group, elapsed }];
    }),
  );
  const rank = (item: (typeof active)[number]): number =>
    (item.group === "running" ? 1e12 : 0) + (item.elapsed ?? 0);
  return [...active]
    .sort((left, right) => rank(right) - rank(left))
    .map(({ run, execution, group, elapsed }) => {
      const name = `${runLabel(run)} · ${execution.executionId}`;
      const age = elapsed === null ? "" : ` ${formatSpan(elapsed)}`;
      if (group === "queued") {
        return {
          key: `${runKey(run)}:${execution.executionId}`,
          status: "queued" as const,
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
        startedAt: parseInstant(execution.startedAt),
        finishedAt: parseInstant(execution.finishedAt),
        outcome: chartGroupOf(execution.status),
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
      <header className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1 pb-3 text-label">
        <h2 className="font-medium text-foreground">Activity</h2>
        <span className="min-w-0 text-muted-foreground tabular-nums">
          {started} started · {finished} finished
          {failed > 0 ? (
            <>
              {" · "}
              <span className="text-status-failed-foreground">{failed} failed</span>
            </>
          ) : null}{" "}
          attempts · drag to narrow the page
        </span>
        <span className="ml-auto">
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

// ── Durations ────────────────────────────────────────────────────────────────

/**
 * One point per finished run: its first start to its last finish. A run whose
 * latest attempt is still active is not finished, whatever an earlier attempt did.
 */
export const durationPointsOf = (rows: readonly WorkspaceRunRow[]): DurationPoint[] =>
  rows.flatMap((run) => {
    const status = chartGroupOf(runPresentationStatus(run));
    if (status === null || !FINISHED_GROUPS.includes(status)) return [];
    const start = parseInstant(runStartedAt(run));
    const end = parseInstant(runFinishedAt(run));
    if (start === null || end === null || end < start) return [];
    return [
      {
        id: runKey(run),
        seconds: (end - start) / 1000,
        status,
        label: `${runLabel(run)} · ${run.experimentName}`,
        href: runHref(run),
      },
    ];
  });

/** What an Overview groups its scope by: projects, experiments, or one swept parameter's values. */
export type GroupKey = "project" | "experiment" | `param:${string}`;

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
