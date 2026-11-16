// ─────────────────────────────────────────────────────────────────────────────
// A run against the runs beside it (L04 decisions 5, Params view): where it
// sits on the experiment's swept axis by the key result, which sibling is its
// baseline, and how each of its parameters relates to the experiment's sweep.
// ─────────────────────────────────────────────────────────────────────────────

import { varyingParameterKeys } from "@/app/renderers/entityWorkbenchData";
import { formatParameter, formatParameterValue } from "@/app/runs/runTitle";
import { type ChartGroupId, chartGroupOf, normalizeStatus, STATUS } from "@/app/status/vocabulary";

/** What the comparison needs of a run. */
export interface ComparedRun {
  id: string;
  title: string;
  parameters: Record<string, unknown>;
  /** The run's status (its latest attempt's). */
  status: string;
  /** Scalar results of its run-result attempt, when loaded. */
  results?: Record<string, unknown> | null;
}

const numeric = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

/**
 * The result that matters for a set of runs: the run's own first numeric
 * result, else the one most siblings report first. Until an experiment
 * declares its key result, the first numeric figure stands in (L04 risk 3).
 */
export const keyMetric = (
  self: Pick<ComparedRun, "results">,
  siblings: readonly Pick<ComparedRun, "results">[],
): string | null => {
  const firstNumeric = (results: ComparedRun["results"]): string | null =>
    Object.entries(results ?? {}).find(([, value]) => numeric(value))?.[0] ?? null;
  const own = firstNumeric(self.results);
  if (own) return own;
  const tally = new Map<string, number>();
  for (const sibling of siblings) {
    const key = firstNumeric(sibling.results);
    if (key) tally.set(key, (tally.get(key) ?? 0) + 1);
  }
  return [...tally.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] ?? null;
};

export interface SweepPoint {
  key: string;
  /** The swept value, printed with its unit. */
  x: string;
  /** Place of `x` on the axis. */
  xOrder: number;
  /** The key result; null when the run has none (failed, still going). */
  y: number | null;
  /** The other varying values: one line per combination. */
  series: string;
  self: boolean;
  status: ChartGroupId | null;
  tip: string;
}

export interface Sweep {
  axisKey: string;
  metric: string;
  points: SweepPoint[];
  /** The run's own line; null on an experiment's chart, where no run is "this run". */
  selfSeries: string | null;
  /** Siblings that reported the metric. */
  siblingsWithResult: number;
}

const compareValues = (left: unknown, right: unknown): number =>
  numeric(left) && numeric(right) ? left - right : String(left).localeCompare(String(right));

/**
 * The run among its siblings on the swept axis. The axis is the varying
 * parameter with the most values, numeric first; every other varying value
 * names a line. Null when nothing varies or no run has the metric.
 */
export const sweepOf = (
  self: ComparedRun,
  siblings: readonly ComparedRun[],
  metric: string | null,
): Sweep | null =>
  sweepAcross([self, ...siblings.filter((run) => run.id !== self.id)], self, metric);

/** Every run of an experiment on its swept axis, none of them "this run" (the experiment Overview). */
export const experimentSweep = (
  runs: readonly ComparedRun[],
  metric: string | null,
): Sweep | null => sweepAcross(runs, null, metric);

const sweepAcross = (
  runs: readonly ComparedRun[],
  self: ComparedRun | null,
  metric: string | null,
): Sweep | null => {
  if (!metric) return null;
  const varying = varyingParameterKeys(runs);
  if (varying.length === 0) return null;
  const valuesOf = (key: string): unknown[] => {
    const seen = new Map<string, unknown>();
    for (const run of runs) {
      if (key in run.parameters) seen.set(JSON.stringify(run.parameters[key]), run.parameters[key]);
    }
    return [...seen.values()].sort(compareValues);
  };
  const axisKey = [...varying].sort((left, right) => {
    const leftNumeric = valuesOf(left).every(numeric) ? 1 : 0;
    const rightNumeric = valuesOf(right).every(numeric) ? 1 : 0;
    return (
      rightNumeric - leftNumeric ||
      valuesOf(right).length - valuesOf(left).length ||
      left.localeCompare(right)
    );
  })[0] as string;
  const axisValues = valuesOf(axisKey);
  const others = varying.filter((key) => key !== axisKey).sort();
  const seriesOf = (run: ComparedRun): string =>
    others.length > 0
      ? others
          .filter((key) => key in run.parameters)
          .map((key) => formatParameter(key, run.parameters[key]))
          .join(" · ")
      : "all runs";
  const points = runs.flatMap((run): SweepPoint[] => {
    if (!(axisKey in run.parameters)) return [];
    const raw = run.results?.[metric];
    const y = numeric(raw) ? raw : null;
    const isSelf = self !== null && run.id === self.id;
    if (y === null && !isSelf) return [];
    const value = run.parameters[axisKey];
    const status = normalizeStatus(run.status);
    return [
      {
        key: run.id,
        x: formatParameterValue(axisKey, value),
        xOrder: axisValues.findIndex((candidate) => compareValues(candidate, value) === 0),
        y,
        series: seriesOf(run),
        self: isSelf,
        status: chartGroupOf(status),
        tip: `${isSelf ? "This run" : run.title} · ${
          y === null ? STATUS[status].word.toLowerCase() : `${metric} ${y.toPrecision(3)}`
        }`,
      },
    ];
  });
  const siblingsWithResult = points.filter((point) => !point.self && point.y !== null).length;
  if (siblingsWithResult === 0) return null;
  return { axisKey, metric, points, selfSeries: self ? seriesOf(self) : null, siblingsWithResult };
};

/**
 * The sibling a run is read against: the one differing in the fewest
 * parameters, a success before anything else, then the first.
 */
export const baselineOf = (
  self: ComparedRun,
  siblings: readonly ComparedRun[],
): ComparedRun | null => {
  const others = siblings.filter((run) => run.id !== self.id);
  const distance = (run: ComparedRun): number =>
    [...new Set([...Object.keys(self.parameters), ...Object.keys(run.parameters)])].filter(
      (key) => JSON.stringify(self.parameters[key]) !== JSON.stringify(run.parameters[key]),
    ).length;
  const succeeded = (run: ComparedRun): number =>
    normalizeStatus(run.status) === "succeeded" ? 0 : 1;
  return (
    [...others].sort(
      (left, right) => distance(left) - distance(right) || succeeded(left) - succeeded(right),
    )[0] ?? null
  );
};

export interface ParameterRow {
  key: string;
  value: string;
  /** Swept: it varies across the experiment. Fixed: every run shares it. */
  role: "swept" | "fixed";
  /** Compared with the baseline; null when there is none. */
  differs: boolean | null;
}

/** The run's parameters: swept ones first, each against the baseline. */
export const parameterRows = (
  self: ComparedRun,
  siblings: readonly ComparedRun[],
  baseline: ComparedRun | null,
): ParameterRow[] => {
  const varying = new Set(
    varyingParameterKeys([self, ...siblings.filter((run) => run.id !== self.id)]),
  );
  return Object.entries(self.parameters)
    .map(
      ([key, value]): ParameterRow => ({
        key,
        value: formatParameterValue(key, value),
        role: varying.has(key) ? "swept" : "fixed",
        differs: baseline
          ? JSON.stringify(baseline.parameters[key]) !== JSON.stringify(value)
          : null,
      }),
    )
    .sort(
      (left, right) =>
        Number(left.role === "fixed") - Number(right.role === "fixed") ||
        left.key.localeCompare(right.key),
    );
};
