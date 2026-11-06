// ─────────────────────────────────────────────────────────────────────────────
// The overview's cross-filter. Brushing the activity clock narrows the scope to
// runs with an attempt in that window; picking a backend narrows it to runs that
// executed there. Both are view state — nothing here is persisted.
// ─────────────────────────────────────────────────────────────────────────────

import { runExecutorFacet } from "@/app/runs/projections";
import type { WorkspaceRunRow } from "@/app/runs/types";

export interface OverviewFilter {
  /** Epoch ms, inclusive. */
  window: [number, number] | null;
  backend: string | null;
}

export const NO_FILTER: OverviewFilter = { window: null, backend: null };

export const isFiltered = (filter: OverviewFilter): boolean =>
  filter.window !== null || filter.backend !== null;

const time = (value: string | null | undefined): number | null => {
  const parsed = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
};

/** Some attempt of the run was alive at a moment inside the window. */
const ranDuring = (run: WorkspaceRunRow, [from, to]: [number, number], now: number): boolean =>
  run.executions.some((execution) => {
    const start = time(execution.startedAt);
    if (start === null) return false;
    const end = time(execution.finishedAt) ?? now;
    return start <= to && end >= from;
  });

/** Same naming as the Backends chart: a run that executed with no backend recorded is "unassigned". */
const ranOn = (run: WorkspaceRunRow, backend: string): boolean => {
  const named = runExecutorFacet(run, "backend");
  return named.length > 0 ? named.includes(backend) : backend === "unassigned";
};

export const applyOverviewFilter = (
  rows: readonly WorkspaceRunRow[],
  filter: OverviewFilter,
  now = Date.now(),
): WorkspaceRunRow[] =>
  rows.filter(
    (run) =>
      (filter.window === null || ranDuring(run, filter.window, now)) &&
      (filter.backend === null || ranOn(run, filter.backend)),
  );
