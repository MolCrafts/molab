/**
 * Cross-scope metric gathering: colour grouping, metric coverage, per-run
 * failure isolation, and the guard that stops a per-step aggregate from
 * silently drawing an empty chart when the step axes do not overlap.
 */

import { describe, expect, it } from "@rstest/core";

import {
  type AggregateOptions,
  aggregateFeasibility,
  buildOverlayConfig,
  normalizeSeries,
  type RunSeries,
} from "./aggregateSeries";
import {
  collectRunSeries,
  type MetricRunSource,
  pickKeySeries,
  type RunAllSeries,
  selectAggregateConfig,
  stepResets,
} from "./multiRunMetrics";
import { PALETTE, type ScalarSeries } from "./RunMetricsView";

const OPTS: AggregateOptions = { xMode: "step", yScale: "linear", smoothing: 0, metricKey: "loss" };

const series = (key: string, ys: number[], steps?: number[]): ScalarSeries => ({
  key,
  group: "",
  points: ys.map((y, i) => ({ step: steps ? steps[i] : i, wall: i, y })),
  latest: ys[ys.length - 1] ?? 0,
});

const run = (key: string, label: string, ys: number[], steps?: number[]): RunSeries => ({
  key,
  label,
  series: series("loss", ys, steps),
});

interface ConfigShape {
  series: Array<{
    id: string;
    label?: string;
    color?: string;
    initialPoints?: { x: number; y: number }[];
  }>;
}

const source = (key: string, label: string): MetricRunSource => ({
  key,
  label,
  title: key,
  coords: { projectId: "p", experimentId: "e", runId: key, executionId: "e01" },
});

describe("colour grouping (comparing across scopes)", () => {
  it("gives each run its own colour when every label differs", () => {
    const config = buildOverlayConfig(
      [run("a", "a", [1]), run("b", "b", [2])],
      OPTS,
    ) as ConfigShape;
    expect(config.series.map((s) => s.color)).toEqual([PALETTE[0], PALETTE[1]]);
  });

  it("gives runs sharing a label one colour, while keeping them separate series", () => {
    const config = buildOverlayConfig(
      [run("r1", "n-series", [1]), run("r2", "n-series", [2]), run("r3", "t-series", [3])],
      OPTS,
    ) as ConfigShape;
    // Two experiments → two colours, but three distinct series ids so molplot's
    // `detail` channel still draws three curves.
    expect(config.series.map((s) => s.color)).toEqual([PALETTE[0], PALETTE[0], PALETTE[1]]);
    expect(config.series.map((s) => s.id)).toEqual(["r1", "r2", "r3"]);
    expect(config.series.map((s) => s.label)).toEqual(["n-series", "n-series", "t-series"]);
  });

  it("cycles the palette by group, not by row", () => {
    const many = Array.from({ length: PALETTE.length + 1 }, (_v, i) => run(`r${i}`, `g${i}`, [i]));
    const config = buildOverlayConfig(many, OPTS) as ConfigShape;
    expect(config.series[PALETTE.length].color).toBe(PALETTE[0]);
  });
});

describe("x-axis modes", () => {
  it("maps each series onto 0..1 under progress, whatever its step units", () => {
    const config = buildOverlayConfig(
      [run("epochs", "a", [1, 2, 3], [0, 1, 2]), run("md", "b", [1, 2, 3], [0, 5000, 10000])],
      { ...OPTS, xMode: "progress" },
    ) as ConfigShape;
    expect(config.series[0].initialPoints?.map((p) => p.x)).toEqual([0, 0.5, 1]);
    expect(config.series[1].initialPoints?.map((p) => p.x)).toEqual([0, 0.5, 1]);
  });

  it("collapses a single-point series to 0 rather than dividing by zero", () => {
    const config = buildOverlayConfig([run("a", "a", [7], [42])], {
      ...OPTS,
      xMode: "progress",
    }) as ConfigShape;
    expect(config.series[0].initialPoints).toEqual([{ x: 0, y: 7 }]);
  });
});

describe("normalizeSeries", () => {
  it("leaves values untouched under none", () => {
    expect(normalizeSeries([2, 4, 8], "none")).toEqual([2, 4, 8]);
  });

  it("expresses values as a factor of the first finite non-zero value", () => {
    expect(normalizeSeries([2, 4, 8], "first")).toEqual([1, 2, 4]);
  });

  it("skips a leading zero when choosing the first-value base", () => {
    expect(normalizeSeries([0, 2, 4], "first")).toEqual([0, 1, 2]);
  });

  it("maps onto 0..1 under minmax, and to 0 for a flat series", () => {
    expect(normalizeSeries([10, 20, 30], "minmax")).toEqual([0, 0.5, 1]);
    expect(normalizeSeries([5, 5], "minmax")).toEqual([0, 0]);
  });
});

describe("aggregateFeasibility", () => {
  it("accepts replicas logged on the same steps", () => {
    const result = aggregateFeasibility([series("loss", [1, 2, 3]), series("loss", [2, 3, 4])]);
    expect(result.ok).toBe(true);
    expect(result.common).toBe(3);
  });

  it("refuses a single run — there is nothing to average across", () => {
    expect(aggregateFeasibility([series("loss", [1, 2, 3])]).ok).toBe(false);
  });

  it("refuses runs whose step axes do not overlap, and says why", () => {
    const result = aggregateFeasibility([
      series("loss", [1, 2, 3], [0, 1, 2]),
      series("loss", [1, 2, 3], [100, 200, 300]),
    ]);
    expect(result.ok).toBe(false);
    expect(result.common).toBe(0);
    expect(result.reason).toContain("share no common step");
  });
});

describe("selectAggregateConfig", () => {
  it("falls back to overlay and reports why when a mean is not meaningful", () => {
    const result = selectAggregateConfig(
      "mean",
      [run("a", "a", [1, 2, 3], [0, 1, 2]), run("b", "b", [1, 2, 3], [100, 200, 300])],
      OPTS,
    );
    expect(result.blockedReason).toContain("share no common step");
    // Overlay keeps both runs visible rather than drawing an empty mean.
    expect((result.config as ConfigShape).series).toHaveLength(2);
  });

  it("computes the mean when the steps do line up", () => {
    const result = selectAggregateConfig(
      "mean",
      [run("a", "a", [1, 3]), run("b", "b", [3, 5])],
      OPTS,
    );
    expect(result.blockedReason).toBeNull();
    expect((result.config as ConfigShape).series[0].initialPoints).toEqual([
      { x: 0, y: 2 },
      { x: 1, y: 4 },
    ]);
  });

  it("never blocks overlay", () => {
    const result = selectAggregateConfig("overlay", [run("a", "a", [1])], OPTS);
    expect(result.blockedReason).toBeNull();
  });
});

describe("metric coverage across a mixed set", () => {
  const perRunAll: RunAllSeries[] = [
    { key: "a", label: "a", title: "a", series: [series("loss", [1]), series("acc", [1])] },
    { key: "b", label: "b", title: "b", series: [series("loss", [1])] },
  ];

  it("skips runs that lack the chosen key rather than emitting an empty curve", () => {
    expect(pickKeySeries(perRunAll, "acc").map((r) => r.key)).toEqual(["a"]);
  });
});

describe("collectRunSeries", () => {
  it("isolates a failing run and keeps the rest", async () => {
    const result = await collectRunSeries(
      async (coords) => {
        if (coords.runId === "bad") throw new Error("gone");
        return [{ t: "scalar", k: "loss", s: 0, w: "2026-01-01T00:00:00Z", v: 1 }];
      },
      [source("good", "g"), source("bad", "b")],
    );
    expect(result.perRunAll.map((r) => r.key)).toEqual(["good"]);
    expect(result.failures).toEqual(["bad"]);
  });

  it("carries the caller's colour group through to the collected series", async () => {
    const result = await collectRunSeries(
      async () => [{ t: "scalar", k: "loss", s: 0, w: "2026-01-01T00:00:00Z", v: 1 }],
      [source("r1", "n-series"), source("r2", "n-series")],
    );
    expect(result.perRunAll.map((r) => r.label)).toEqual(["n-series", "n-series"]);
  });
});

describe("stepResets", () => {
  it("counts nothing for a monotonic series", () => {
    expect(stepResets(series("d", [1, 2, 3], [0, 1000, 2000]))).toBe(0);
  });

  it("ignores the repeated row at a LAMMPS block boundary", () => {
    // A `run` command reprints its starting step, so the last row of one block
    // and the first of the next are the same step by design.
    expect(stepResets(series("d", [1, 2, 3, 4], [0, 1000, 1000, 2000]))).toBe(0);
  });

  it("counts a counter that actually goes backwards", () => {
    // Minimisation iterations, then `reset_timestep 0`, then MD timesteps.
    expect(stepResets(series("d", [1, 2, 3, 4], [0, 10748, 0, 1000]))).toBe(1);
  });

  it("counts each reset separately", () => {
    expect(stepResets(series("d", [1, 2, 3, 4], [5, 0, 7, 0]))).toBe(2);
  });
});
