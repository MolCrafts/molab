// Shared derivations for the entity-Overview dashboards. Keeps the status
// roll-up and duration formatting in one place so the Experiment / Run /
// Project overviews report identical numbers.

import type { RunSummary } from "@/app/types";

/** Wall-clock seconds of runs that have both a start and a finish. */
export const finishedDurationSeconds = (
  runs: readonly Pick<RunSummary, "startedAt" | "finishedAt">[],
): number[] =>
  runs.flatMap((run) => {
    if (!run.startedAt || !run.finishedAt) return [];
    const ms = Date.parse(run.finishedAt) - Date.parse(run.startedAt);
    return Number.isFinite(ms) && ms >= 0 ? [ms / 1000] : [];
  });

/** Compact scalar rendering for params/results cells. */
export const formatScalar = (value: unknown): string => {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};
