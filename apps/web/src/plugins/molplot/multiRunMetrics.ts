/**
 * Gathering one metric across several runs.
 *
 * Everything here is pure and free of React, the comparison set, and the
 * workspace tree: a run is a `MetricRunSource` — where to read it, what to call
 * the curve, and which colour group it belongs to. That keeps molplot's side of
 * the boundary about series and specs, and leaves "which runs" to the caller.
 *
 * The split between `key` and `label` is the whole mechanism for comparing
 * across scopes: `key` is unique per run and becomes the molplot series id, so
 * every run is its own polyline; `label` is shared by a group and becomes the
 * series label, which `lineSpec` dedupes into one colour and one legend entry.
 */

import type { MetricRecordSample as MetricRecord } from "@/lib/contribution-types";

import type { LineChartConfig } from "@/plugins/molplot";
import {
  type AggregateOptions,
  aggregateFeasibility,
  buildErrorbandConfig,
  buildMeanConfig,
  buildOverlayConfig,
  type RunSeries,
} from "./aggregateSeries";
import { buildScalarSeries, type ScalarSeries } from "./RunMetricsView";
import type { ExecutionCoords } from "./read-metrics";

export type AggregateOp = "overlay" | "mean" | "errorbar";

/** One run to read, plus how it should appear on the chart. */
export interface MetricRunSource {
  /** Unique per run — becomes the molplot series id (one polyline). */
  key: string;
  /** Colour group — runs sharing a label share a colour and a legend entry. */
  label: string;
  /** Human name, for failure lists and tooltips. */
  title: string;
  coords: ExecutionCoords;
}

/** Injectable reader so the orchestration is testable without the network. */
export type MetricsFetcher = (coords: ExecutionCoords) => Promise<MetricRecord[]>;

export interface RunAllSeries {
  key: string;
  label: string;
  title: string;
  /** Every scalar series the run logged (all keys). */
  series: ScalarSeries[];
}

export interface CollectResult {
  perRunAll: RunAllSeries[];
  /** Titles of runs whose read failed — surfaced, never fatal. */
  failures: string[];
}

/**
 * Read every source in parallel, isolating per-run failures.
 *
 * One unreadable run lands in `failures` and the rest still resolve: a set
 * gathered across workspaces will routinely contain a run whose attempt was
 * cleaned up or whose remote is down, and that must not blank the chart.
 */
export const collectRunSeries = async (
  fetcher: MetricsFetcher,
  sources: readonly MetricRunSource[],
): Promise<CollectResult> => {
  const settled = await Promise.all(
    sources.map(async (source) => {
      try {
        const records = await fetcher(source.coords);
        return { source, series: buildScalarSeries(records), ok: true as const };
      } catch {
        return { source, series: [] as ScalarSeries[], ok: false as const };
      }
    }),
  );

  const perRunAll: RunAllSeries[] = [];
  const failures: string[] = [];
  for (const result of settled) {
    if (result.ok) {
      perRunAll.push({
        key: result.source.key,
        label: result.source.label,
        title: result.source.title,
        series: result.series,
      });
    } else {
      failures.push(result.source.title);
    }
  }
  return { perRunAll, failures };
};

/**
 * Places where a series' step axis goes backwards.
 *
 * A solver log is not one monotonic timeline. A LAMMPS run that minimises
 * before it integrates prints both under a column called `Step`, and those are
 * different quantities — minimiser iterations, then timesteps — so the second
 * block starts over at 0. `reset_timestep` does the same thing deliberately.
 * Concatenated onto one axis the curve doubles back on itself, which reads as
 * corrupt data when the file is in fact exactly right.
 *
 * Equal consecutive steps are not counted: a `run` command reprints its
 * starting step, so every block boundary repeats one row by design.
 */
export const stepResets = (series: ScalarSeries): number => {
  let resets = 0;
  for (let i = 1; i < series.points.length; i += 1) {
    if (series.points[i].step < series.points[i - 1].step) resets += 1;
  }
  return resets;
};

/** For the chosen key, take each run's matching series; skip runs lacking it. */
export const pickKeySeries = (
  perRunAll: readonly RunAllSeries[],
  metricKey: string,
): RunSeries[] => {
  const out: RunSeries[] = [];
  for (const { key, label, series } of perRunAll) {
    const match = series.find((s) => s.key === metricKey);
    if (match) out.push({ key, label, series: match });
  }
  return out;
};

export interface AggregateResult {
  config: LineChartConfig;
  /** Steps present in some run but not all, excluded from a per-step aggregate. */
  dropped: number;
  /** Why the requested op could not run, when it fell back to overlay. */
  blockedReason: string | null;
}

/**
 * Dispatch the chosen op onto the pure builders.
 *
 * `mean` and `errorbar` fall back to `overlay` when the step axes do not
 * actually overlap, and say why. Silently drawing the empty chart that a
 * zero-length step intersection produces reads as a bug, not as the axis
 * mismatch it is.
 */
export const selectAggregateConfig = (
  op: AggregateOp,
  perRun: RunSeries[],
  options: AggregateOptions,
): AggregateResult => {
  if (op === "overlay") {
    return { config: buildOverlayConfig(perRun, options), dropped: 0, blockedReason: null };
  }
  const series = perRun.map((r) => r.series);
  const feasibility = aggregateFeasibility(series);
  if (!feasibility.ok) {
    return {
      config: buildOverlayConfig(perRun, options),
      dropped: feasibility.dropped,
      blockedReason: feasibility.reason,
    };
  }
  const built =
    op === "mean" ? buildMeanConfig(series, options) : buildErrorbandConfig(series, options);
  return { config: built.config, dropped: built.dropped, blockedReason: null };
};
