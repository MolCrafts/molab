// Shared derivations for the entity-Overview dashboards. Keeps the status
// roll-up and duration formatting in one place so the Experiment / Run /
// Project overviews report identical numbers.

import { groupForStatus } from "@/app/runs/statusGroups";
import type { RunSummary } from "@/app/types";

export interface RunStatusCounts {
  total: number;
  running: number;
  pending: number;
  succeeded: number;
  failed: number;
  cancelled: number;
}

/** Roll a set of runs up into the canonical status groups. */
export const countRunStatuses = (runs: Pick<RunSummary, "status">[]): RunStatusCounts => {
  const counts: RunStatusCounts = {
    total: runs.length,
    running: 0,
    pending: 0,
    succeeded: 0,
    failed: 0,
    cancelled: 0,
  };
  for (const run of runs) {
    const group = groupForStatus(run.status);
    if (group) counts[group] += 1;
  }
  return counts;
};

/** Success rate over *terminal* runs only (excludes running/pending). */
export const successRate = (counts: RunStatusCounts): number | null => {
  const terminal = counts.succeeded + counts.failed + counts.cancelled;
  if (terminal === 0) return null;
  return (counts.succeeded / terminal) * 100;
};

/** Human duration between two ISO instants, or null if either is missing. */
export const formatDuration = (startIso: string | null, endIso: string | null): string | null => {
  if (!startIso || !endIso) return null;
  const start = Date.parse(startIso);
  const end = Date.parse(endIso);
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  const ms = Math.max(0, end - start);
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 2 : 1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds - minutes * 60);
  return `${minutes}m${remainder.toString().padStart(2, "0")}s`;
};

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
