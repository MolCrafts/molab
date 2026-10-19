// Run summaries → gauge inputs. One place, so the project, experiment and
// workspace overviews place the same run on the same dot.

import type { DurationPoint, SweepAxis } from "@/app/components/entity";
import type { AxisBreakdownSummary } from "@/app/renderers/entityWorkbenchData";
import { groupForStatus } from "@/app/runs/statusGroups";
import type { RunSummary } from "@/app/types";

const seconds = (run: Pick<RunSummary, "startedAt" | "finishedAt">): number | null => {
  if (!run.startedAt || !run.finishedAt) return null;
  const ms = Date.parse(run.finishedAt) - Date.parse(run.startedAt);
  return Number.isFinite(ms) && ms >= 0 ? ms / 1000 : null;
};

export const runLabel = (run: Pick<RunSummary, "id" | "name">): string => run.name || run.id;

/** One dot per run that has both a start and a finish. */
export const durationPoints = (
  runs: readonly RunSummary[],
  hrefFor: (run: RunSummary) => string,
): DurationPoint[] =>
  runs.flatMap((run) => {
    const value = seconds(run);
    return value === null
      ? []
      : [
          {
            id: run.id,
            seconds: value,
            status: groupForStatus(run.status),
            label: runLabel(run),
            href: hrefFor(run),
          },
        ];
  });

export const sweepAxes = (breakdowns: readonly AxisBreakdownSummary[]): SweepAxis[] =>
  breakdowns.map((axis) => ({
    key: axis.key,
    cells: axis.buckets.map((bucket) => ({
      value: bucket.value,
      unset: bucket.unset,
      runCount: bucket.runs.length,
    })),
  }));

/** Values a declared sweep listed that no run has used yet. */
export const unrunValueCount = (axes: readonly SweepAxis[]): number =>
  axes.reduce(
    (total, axis) => total + axis.cells.filter((cell) => !cell.unset && cell.runCount === 0).length,
    0,
  );

/** Newest failed run that left an error message. */
export const latestFailure = (runs: readonly RunSummary[]): RunSummary | null =>
  [...runs]
    .filter((run) => groupForStatus(run.status) === "failed")
    .sort(
      (left, right) =>
        (Date.parse(right.finishedAt ?? right.updatedAt) || 0) -
        (Date.parse(left.finishedAt ?? left.updatedAt) || 0),
    )[0] ?? null;
