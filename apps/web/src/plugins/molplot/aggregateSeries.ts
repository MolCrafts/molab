import type { LineChartConfig, LineSeriesConfig } from "@/plugins/molplot";
import { smoothEma } from "@/plugins/molplot/smoothing";

import { PALETTE, type ScalarSeries } from "./RunMetricsView";

/**
 * Pure builders for Mode-A multi-run metrics aggregation: take per-run scalar
 * series for a single metric key and fold them into a molplot LineChartConfig
 * three ways — overlay (one line per run), mean (per-step arithmetic mean), and
 * errorbar (mean ± sample std).
 *
 * Replicas are assumed to be logged on identical steps; alignment is therefore
 * a strict common-step intersection with NO interpolation or binning. Steps that
 * are not shared by every run are dropped and counted (`dropped`), mirroring the
 * `parseErrors` counter convention of the single-run view.
 *
 * All functions are pure (no fetch, no React) so they run directly under the
 * repo's node test environment — see aggregateSeries.test.ts.
 */

export type XMode = "step" | "wall" | "progress";
export type YScale = "linear" | "log";
/** Per-series rescaling, for overlaying metrics whose units do not match. */
export type YNormalize = "none" | "first" | "minmax";

export interface AggregateOptions {
  xMode: XMode;
  yScale: YScale;
  /** EMA weight in [0, 1); 0 disables smoothing. */
  smoothing: number;
  /** The metric key being aggregated — used for axis + series labels. */
  metricKey: string;
  /** Per-series rescaling. Defaults to "none". */
  normalize?: YNormalize;
}

/**
 * One selected run's scalar series, with identity and colour-group separated.
 *
 * `key` is the run's own address and becomes the molplot series `id`, which
 * `lineSpec` puts on the `detail` channel — one polyline per run, always.
 * `label` becomes the series `label`, which `lineSpec` dedupes to build the
 * colour scale and the legend. Setting several runs to the same `label` is
 * therefore how "colour by experiment" works: one legend entry, one colour,
 * still N separate curves.
 */
export interface RunSeries {
  key: string;
  label: string;
  series: ScalarSeries;
}

type ScalarPoint = ScalarSeries["points"][number];

interface AlignedStep {
  step: number;
  /** Mean wall-clock across runs at this step (runs may differ slightly). */
  wall: number;
  /** y value from each run at this step, in run order. */
  ys: number[];
}

export interface AlignResult {
  points: AlignedStep[];
  /** Distinct steps present in some run but not all — excluded from aggregation. */
  dropped: number;
}

/**
 * Intersect the step axes of every series. A step survives only if every run
 * has a sample at it; everything else is dropped (and counted). Points are
 * returned sorted by step ascending.
 */
export const alignSteps = (series: ScalarSeries[]): AlignResult => {
  if (series.length === 0) {
    return { points: [], dropped: 0 };
  }

  const byStep = series.map((s) => {
    const m = new Map<number, ScalarPoint>();
    for (const p of s.points) {
      m.set(p.step, p);
    }
    return m;
  });

  const unionSteps = new Set<number>();
  for (const m of byStep) {
    for (const step of m.keys()) {
      unionSteps.add(step);
    }
  }

  const common = Array.from(unionSteps)
    .filter((step) => byStep.every((m) => m.has(step)))
    .sort((a, b) => a - b);

  const points: AlignedStep[] = common.map((step) => {
    const perRun = byStep.map((m) => m.get(step) as ScalarPoint);
    const wall = perRun.reduce((acc, p) => acc + p.wall, 0) / perRun.length;
    return { step, wall, ys: perRun.map((p) => p.y) };
  });

  return { points, dropped: unionSteps.size - common.length };
};

const mean = (xs: number[]): number => xs.reduce((acc, x) => acc + x, 0) / xs.length;

/** Sample standard deviation (n-1 denominator); 0 for a single sample. */
const sampleStd = (xs: number[]): number => {
  if (xs.length < 2) {
    return 0;
  }
  const m = mean(xs);
  const variance = xs.reduce((acc, x) => acc + (x - m) ** 2, 0) / (xs.length - 1);
  return Math.sqrt(variance);
};

/** Shared axis / theme block, mirroring RunMetricsView's chart config. */
const X_LABEL: Record<XMode, string> = {
  step: "step",
  wall: "wall time",
  progress: "progress (0-1)",
};

const baseConfig = (
  series: LineSeriesConfig[],
  options: Pick<AggregateOptions, "xMode" | "yScale" | "metricKey" | "normalize">,
): LineChartConfig => ({
  series,
  xAxis: {
    label: X_LABEL[options.xMode],
    type: "linear",
  },
  yAxis: {
    type: options.yScale,
    label: yAxisLabel(options.metricKey, options.normalize ?? "none"),
  },
  hovertemplate: "%{y:.6g}<extra></extra>",
  hovermode: "x unified",
  showLegend: true,
  theme: "auto",
});

// Only the x-axis fields are read, so accept any point carrying them — this lets
// both ScalarPoint and the aggregated AlignedStep (which has no single `y`) pass.
const xValue = (point: Pick<ScalarPoint, "step" | "wall">, xMode: XMode): number =>
  xMode === "step" ? point.step : point.wall;

/**
 * X values for one series under the chosen mode.
 *
 * `progress` maps each series onto [0, 1] by its own extent. Comparing an
 * epoch-indexed training run against an MD run indexed in timesteps is
 * meaningless on a shared step axis — the two axes are different quantities
 * that happen to share a name — so this offers "how far through" instead of
 * pretending the numbers are commensurable. A single-point series collapses to
 * 0 rather than dividing by zero.
 */
const xValues = (points: readonly Pick<ScalarPoint, "step" | "wall">[], xMode: XMode): number[] => {
  const raw = points.map((point) => xValue(point, xMode === "progress" ? "step" : xMode));
  if (xMode !== "progress") return raw;
  const lo = Math.min(...raw);
  const hi = Math.max(...raw);
  const span = hi - lo;
  return span === 0 ? raw.map(() => 0) : raw.map((value) => (value - lo) / span);
};

/**
 * Rescale one series so curves with different units share a y-axis.
 *
 * `first` divides by the first finite value, turning every curve into a factor
 * of where it started; `minmax` maps each onto [0, 1]. Both are per-series by
 * construction — that is the whole point — so the y-axis is a ratio, and the
 * label says so.
 */
export const normalizeSeries = (ys: readonly number[], mode: YNormalize): number[] => {
  if (mode === "none" || ys.length === 0) return [...ys];
  if (mode === "first") {
    const base = ys.find((y) => Number.isFinite(y) && y !== 0);
    return base === undefined ? [...ys] : ys.map((y) => y / base);
  }
  const finite = ys.filter((y) => Number.isFinite(y));
  const lo = Math.min(...finite);
  const hi = Math.max(...finite);
  const span = hi - lo;
  return span === 0 ? ys.map(() => 0) : ys.map((y) => (y - lo) / span);
};

/** Axis label that admits when the values are no longer the metric's own. */
const yAxisLabel = (metricKey: string, normalize: YNormalize): string =>
  normalize === "first"
    ? `${metricKey} (relative to first)`
    : normalize === "minmax"
      ? `${metricKey} (normalised 0-1)`
      : metricKey;

const applySmoothing = (ys: number[], smoothing: number): number[] =>
  smoothing > 0 ? smoothEma(ys, smoothing) : ys;

/**
 * Overlay: one line per run, palette-cycled in run order. Each run keeps its own
 * x-axis (steps need not be aligned for a pure overlay).
 */
export const buildOverlayConfig = (
  perRun: RunSeries[],
  options: AggregateOptions,
): LineChartConfig => {
  // Colour follows the *group*, not the row order. Runs sharing a label (all
  // the seeds of one experiment, say) must come out one colour and one legend
  // entry; palette-by-index would scatter them across the wheel and lose the
  // grouping the user asked for.
  const groups: string[] = [];
  for (const { label } of perRun) {
    if (!groups.includes(label)) groups.push(label);
  }

  const series: LineSeriesConfig[] = perRun.map(({ key, label, series: s }) => {
    const xs = xValues(s.points, options.xMode);
    const ys = applySmoothing(
      normalizeSeries(
        s.points.map((p) => p.y),
        options.normalize ?? "none",
      ),
      options.smoothing,
    );
    return {
      id: key,
      label,
      color: PALETTE[groups.indexOf(label) % PALETTE.length],
      width: 2,
      mode: "lines+markers",
      initialPoints: ys.map((y, i) => ({ x: xs[i], y })),
    };
  });
  return baseConfig(series, options);
};

/**
 * Whether a per-step aggregate is meaningful for this set.
 *
 * `alignSteps` intersects step axes exactly, with no interpolation, so runs
 * that were logged on different grids — epochs against timesteps, or two
 * solvers with different thermo frequencies — share almost nothing. Averaging
 * across one or zero common steps produces an empty or single-point chart that
 * looks like a bug rather than the mismatch it is, so callers ask first and
 * show the reason instead of the empty chart.
 */
export interface AlignFeasibility {
  ok: boolean;
  common: number;
  dropped: number;
  reason: string | null;
}

export const aggregateFeasibility = (series: ScalarSeries[]): AlignFeasibility => {
  if (series.length < 2) {
    return {
      ok: false,
      common: 0,
      dropped: 0,
      reason: "Per-step aggregation needs at least two runs with this metric.",
    };
  }
  const { points, dropped } = alignSteps(series);
  if (points.length < 2) {
    return {
      ok: false,
      common: points.length,
      dropped,
      reason:
        points.length === 0
          ? "The selected runs share no common step, so there is nothing to average. Use Overlay."
          : "The selected runs share only one common step. Use Overlay.",
    };
  }
  return { ok: true, common: points.length, dropped, reason: null };
};

/**
 * Per-step arithmetic mean over the common steps. Returns a single synthetic
 * ScalarSeries plus the dropped-step count, so callers can both render it and
 * surface alignment loss.
 */
export const buildMeanSeries = (
  series: ScalarSeries[],
): { mean: ScalarSeries; dropped: number } => {
  const { points, dropped } = alignSteps(series);
  const meanPoints: ScalarPoint[] = points.map((p) => ({
    step: p.step,
    wall: p.wall,
    y: mean(p.ys),
  }));
  const key = series[0]?.key ?? "";
  return {
    mean: {
      key: `${key} (mean)`,
      group: series[0]?.group ?? "",
      points: meanPoints,
      latest: meanPoints[meanPoints.length - 1]?.y ?? 0,
    },
    dropped,
  };
};

/** Mean line as a single-series config (the `mean` aggregation op). */
export const buildMeanConfig = (
  series: ScalarSeries[],
  options: AggregateOptions,
): { config: LineChartConfig; dropped: number } => {
  const { mean: meanSeries, dropped } = buildMeanSeries(series);
  const xs = xValues(meanSeries.points, options.xMode);
  const ys = applySmoothing(
    normalizeSeries(
      meanSeries.points.map((p) => p.y),
      options.normalize ?? "none",
    ),
    options.smoothing,
  );
  const line: LineSeriesConfig = {
    id: "mean",
    label: `${options.metricKey} (mean)`,
    color: PALETTE[0],
    width: 2,
    mode: "lines+markers",
    initialPoints: ys.map((y, i) => ({ x: xs[i], y })),
  };
  return { config: baseConfig([line], options), dropped };
};

// molplot's LineChart has no native filled-band / error_y trace — LineSeriesConfig
// exposes only id/label/color/width/opacity/mode/initialPoints (see
// @molcrafts/molplot types). The ±std band is therefore drawn as two faint
// boundary lines (upper/lower) around the solid mean line.
const BAND_OPACITY = 0.25;

/**
 * Errorbar: per-step mean ± sample std, rendered as a mean line plus faded
 * upper/lower boundary lines. Smoothing is applied to the mean before offsetting
 * by the (unsmoothed) per-step std so the band tracks the displayed mean.
 */
export const buildErrorbandConfig = (
  series: ScalarSeries[],
  options: AggregateOptions,
): { config: LineChartConfig; dropped: number } => {
  const { points, dropped } = alignSteps(series);
  const xs = xValues(points, options.xMode);
  // The band is offset by the raw per-step spread, but both mean and
  // spread are rescaled together so the band still brackets the drawn mean.
  const normalize = options.normalize ?? "none";
  const means = applySmoothing(
    normalizeSeries(
      points.map((p) => mean(p.ys)),
      normalize,
    ),
    options.smoothing,
  );
  const rawMeans = points.map((p) => mean(p.ys));
  const scale =
    normalize === "none"
      ? 1
      : (() => {
          const before = Math.max(...rawMeans) - Math.min(...rawMeans);
          const after = Math.max(...means) - Math.min(...means);
          return before === 0 ? 1 : after / before;
        })();
  const stds = points.map((p) => sampleStd(p.ys) * scale);
  const color = PALETTE[0];

  const upper: LineSeriesConfig = {
    id: "upper",
    label: "+std",
    color,
    width: 1,
    opacity: BAND_OPACITY,
    initialPoints: means.map((m, i) => ({ x: xs[i], y: m + stds[i] })),
  };
  const lower: LineSeriesConfig = {
    id: "lower",
    label: "-std",
    color,
    width: 1,
    opacity: BAND_OPACITY,
    initialPoints: means.map((m, i) => ({ x: xs[i], y: m - stds[i] })),
  };
  const meanLine: LineSeriesConfig = {
    id: "mean",
    label: `${options.metricKey} (mean)`,
    color,
    width: 2,
    mode: "lines+markers",
    initialPoints: means.map((m, i) => ({ x: xs[i], y: m })),
  };

  return { config: baseConfig([upper, lower, meanLine], options), dropped };
};
