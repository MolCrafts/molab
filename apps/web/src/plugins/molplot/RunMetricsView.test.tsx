/**
 * Tests for the pure metric-series builders behind the shared RunMetricsView
 * component (node env, no jsdom — the builders are exercised directly).
 */

import { describe, expect, it } from "@rstest/core";
import type { MetricRecordSample as MetricRecord } from "@/lib/contribution-types";
import { lineChartStructureKey, planSeriesUpdate } from "./MolplotLineChart";
import { buildLineChartConfig, buildScalarSeries, groupSeries } from "./RunMetricsView";

// Two distinct scalar keys across several (intentionally out-of-order) steps,
// plus one non-scalar record that must be ignored by buildScalarSeries.
const SAMPLE_RECORDS: MetricRecord[] = [
  { t: "scalar", k: "train/loss", s: 2, w: "2026-06-15T00:00:02Z", v: 0.5 },
  { t: "scalar", k: "eval/loss", s: 1, w: "2026-06-15T00:00:01Z", v: 0.9 },
  { t: "scalar", k: "train/loss", s: 0, w: "2026-06-15T00:00:00Z", v: 1.0 },
  { t: "scalar", k: "train/loss", s: 1, w: "2026-06-15T00:00:01Z", v: 0.7 },
  { t: "scalar", k: "eval/loss", s: 0, w: "2026-06-15T00:00:00Z", v: 1.2 },
  { t: "histogram", k: "weights/layer0", s: 0, w: "2026-06-15T00:00:00Z", v: [1, 2, 3] },
];

interface ScalarPointShape {
  step: number;
  wall: number;
  y: number;
}

interface ScalarSeriesShape {
  key: string;
  group: string;
  points: ScalarPointShape[];
  latest: number;
}

describe("buildScalarSeries (ac-001)", () => {
  it("returns exactly one series per distinct scalar key, ignoring non-scalar records", () => {
    const series = buildScalarSeries(SAMPLE_RECORDS) as ScalarSeriesShape[];
    expect(series).toHaveLength(2);
    const keys = series.map((s) => s.key).sort();
    expect(keys).toEqual(["eval/loss", "train/loss"]);
  });

  it("sorts each series' points by step ascending", () => {
    const series = buildScalarSeries(SAMPLE_RECORDS) as ScalarSeriesShape[];
    const train = series.find((s) => s.key === "train/loss");
    expect(train).toBeDefined();
    const steps = (train as ScalarSeriesShape).points.map((p) => p.step);
    expect(steps).toEqual([0, 1, 2]);
    const ys = (train as ScalarSeriesShape).points.map((p) => p.y);
    expect(ys).toEqual([1.0, 0.7, 0.5]);
  });
});

describe("groupSeries (ac-001)", () => {
  it("buckets each series under the prefix before the first slash", () => {
    const series = buildScalarSeries(SAMPLE_RECORDS) as ScalarSeriesShape[];
    const grouped = groupSeries(series) as Array<[string, ScalarSeriesShape[]]>;
    const groupNames = grouped.map(([name]) => name).sort();
    expect(groupNames).toEqual(["eval", "train"]);

    const byGroup = new Map(grouped);
    const evalSeries = byGroup.get("eval");
    const trainSeries = byGroup.get("train");
    expect(evalSeries?.map((s) => s.key)).toEqual(["eval/loss"]);
    expect(trainSeries?.map((s) => s.key)).toEqual(["train/loss"]);
  });
});

describe("buildLineChartConfig (ac-001)", () => {
  it("emits at least one series whose initialPoints mirror the scalar points (x=step, y=value)", () => {
    const series = buildScalarSeries(SAMPLE_RECORDS) as ScalarSeriesShape[];
    const train = series.find((s) => s.key === "train/loss") as ScalarSeriesShape;

    const config = buildLineChartConfig(train, {
      xMode: "step",
      yScale: "linear",
      smoothing: 0,
      color: "oklch(0.55 0.18 255)",
    }) as { series: Array<{ initialPoints: Array<{ x: number; y: number }> }> };

    expect(Array.isArray(config.series)).toBe(true);
    expect(config.series.length).toBeGreaterThanOrEqual(1);

    const primary = config.series[0];
    expect(primary.initialPoints).toEqual([
      { x: 0, y: 1.0 },
      { x: 1, y: 0.7 },
      { x: 2, y: 0.5 },
    ]);
  });

  it("keeps the Vega container structure key stable when only points change", () => {
    const series = buildScalarSeries(SAMPLE_RECORDS) as ScalarSeriesShape[];
    const train = series.find((s) => s.key === "train/loss") as ScalarSeriesShape;
    const a = buildLineChartConfig(train, {
      xMode: "step",
      yScale: "linear",
      smoothing: 0,
      color: "oklch(0.55 0.18 255)",
    });
    const grown = {
      ...train,
      points: [...train.points, { step: 3, wall: train.points[0].wall, y: 0.4 }],
    };
    const b = buildLineChartConfig(grown, {
      xMode: "step",
      yScale: "linear",
      smoothing: 0,
      color: "oklch(0.55 0.18 255)",
    });
    expect(lineChartStructureKey(a)).toBe(lineChartStructureKey(b));
  });

  it("filters a lone spike before EMA, leaving the faded raw trace intact", () => {
    const ys = Array.from({ length: 24 }, () => 1);
    ys[20] = 1000;
    const series: ScalarSeriesShape = {
      key: "train/loss",
      group: "train",
      points: ys.map((y, step) => ({ step, wall: step, y })),
      latest: 1,
    };
    const options = {
      xMode: "step" as const,
      yScale: "linear" as const,
      smoothing: 0.6,
      color: "oklch(0.55 0.18 255)",
    };
    const filtered = buildLineChartConfig(series, { ...options, spikeFilter: true, spikeSigma: 4 });
    const unfiltered = buildLineChartConfig(series, { ...options, spikeFilter: false });

    expect(filtered.series).toHaveLength(2);
    expect(filtered.series[0].initialPoints[20]).toEqual({ x: 20, y: 1000 });
    expect(filtered.series[1].initialPoints[20].y).toBeLessThan(2);
    expect(unfiltered.series[1].initialPoints[20].y).toBeGreaterThan(
      filtered.series[1].initialPoints[20].y + 1,
    );
  });
});

describe("planSeriesUpdate", () => {
  const p = (x: number, y: number) => ({ x, y });

  it("appends only the tail when the prefix matches the cursor", () => {
    const plan = planSeriesUpdate({ length: 2, lastX: 1, lastY: 0.7 }, [
      p(0, 1),
      p(1, 0.7),
      p(2, 0.5),
      p(3, 0.4),
    ]);
    expect(plan).toEqual({ op: "append", points: [p(2, 0.5), p(3, 0.4)] });
  });

  it("noops when length and last point are unchanged", () => {
    expect(planSeriesUpdate({ length: 2, lastX: 1, lastY: 0.7 }, [p(0, 1), p(1, 0.7)])).toEqual({
      op: "noop",
    });
  });

  it("replaces when the stream is shorter or the hinge moved", () => {
    expect(planSeriesUpdate({ length: 3, lastX: 2, lastY: 0.5 }, [p(0, 1)])).toEqual({
      op: "replace",
    });
    expect(
      planSeriesUpdate({ length: 2, lastX: 9, lastY: 9 }, [p(0, 1), p(1, 0.7), p(2, 0.5)]),
    ).toEqual({ op: "replace" });
  });
});
