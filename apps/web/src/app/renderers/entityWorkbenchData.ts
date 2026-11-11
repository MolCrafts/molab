import type { ExperimentSummary, ProjectSummary, RunSummary } from "@/app/types";

export interface ProjectSnapshotCompleteness {
  /** Authoritative server total, or null when the shallow summary did not report it. */
  experimentCount: number | null;
  /** Sum of authoritative per-experiment totals, or null when any child total is unknown. */
  runCount: number | null;
  experimentsComplete: boolean;
  runsComplete: boolean;
}

export interface ExperimentRunCompleteness {
  runCount: number | null;
  runsComplete: boolean;
}

export interface ParameterAxisSummary {
  key: string;
  values: string[];
  count: number;
}

/** One value of a swept parameter, with the runs that used it and their status mix. */
const reportedCount = (value: number | null | undefined): number | null =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;

/** Distinguish authoritative totals from the lazy client snapshot. Consumers
 * must gate status distributions and rates on the corresponding complete flag. */
export const projectSnapshotCompleteness = (
  project: Pick<ProjectSummary, "experimentCount">,
  experiments: Pick<ExperimentSummary, "runCount">[],
  runs: Pick<RunSummary, "id">[],
): ProjectSnapshotCompleteness => {
  const experimentCount = reportedCount(project.experimentCount);
  const experimentsComplete = experimentCount !== null && experiments.length === experimentCount;
  const childRunCounts = experiments.map((experiment) => reportedCount(experiment.runCount));
  const runCount =
    experimentsComplete && childRunCounts.every((count) => count !== null)
      ? childRunCounts.reduce<number>((total, count) => total + (count ?? 0), 0)
      : null;

  return {
    experimentCount,
    runCount,
    experimentsComplete,
    runsComplete: runCount !== null && runs.length === runCount,
  };
};

export const experimentRunCompleteness = (
  experiment: Pick<ExperimentSummary, "runCount">,
  loadedRunCount: number,
): ExperimentRunCompleteness => {
  const runCount = reportedCount(experiment.runCount);
  return {
    runCount,
    runsComplete: runCount !== null && loadedRunCount === runCount,
  };
};

const stringifyAxisValue = (value: unknown): string => {
  if (Array.isArray(value)) return value.map(stringifyAxisValue).join(", ");
  if (value === null || value === undefined) return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

export const buildParameterAxes = (
  experiment: Pick<ExperimentSummary, "parameterSpace">,
  runs: Pick<RunSummary, "parameters">[],
): ParameterAxisSummary[] => {
  const valuesByKey = new Map<string, Set<string>>();
  const ensure = (key: string): Set<string> => {
    const existing = valuesByKey.get(key);
    if (existing) return existing;
    const next = new Set<string>();
    valuesByKey.set(key, next);
    return next;
  };

  for (const [key, value] of Object.entries(experiment.parameterSpace ?? {})) {
    const bucket = ensure(key);
    if (Array.isArray(value)) {
      for (const item of value) bucket.add(stringifyAxisValue(item));
    } else {
      bucket.add(stringifyAxisValue(value));
    }
  }

  for (const run of runs) {
    for (const [key, value] of Object.entries(run.parameters ?? {})) {
      ensure(key).add(stringifyAxisValue(value));
    }
  }

  return [...valuesByKey.entries()].map(([key, values]) => ({
    key,
    values: [...values].filter(Boolean),
    count: values.size,
  }));
};

/**
 * Parameters whose value differs between the runs, in first-seen order — the
 * axes a grouping can split on and a run's coordinates in its sweep. A
 * parameter every run shares is not an axis; a run that never set one is filed
 * apart, not counted as a value.
 */
export const varyingParameterKeys = (runs: readonly Pick<RunSummary, "parameters">[]): string[] =>
  buildParameterAxes({ parameterSpace: {} }, [...runs])
    .filter((axis) => axis.count > 1)
    .map((axis) => axis.key);
