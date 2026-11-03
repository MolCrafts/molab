// Sweep axes → the Parameters tab's matrix inputs.

import type { SweepAxis } from "@/app/components/entity";
import type { AxisBreakdownSummary } from "@/app/renderers/entityWorkbenchData";

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
