import { compileVegaLite } from "@molcrafts/ui-vega-lite";
import { describe, expect, it } from "@rstest/core";
import type { OverviewPalette } from "@/app/components/entity/gauges/vega/common";
import { type MetricRun, metricChartData, metricSpec } from "./metricChartModel";

const run = (id: string, status: string, parameters: Record<string, unknown>): MetricRun => ({
  id,
  status,
  parameters,
  title: id,
});

const RUNS: MetricRun[] = [
  run("a", "succeeded", { timestep_fs: 1, ensemble: "nve" }),
  run("b", "succeeded", { timestep_fs: 0.5, ensemble: "nve" }),
  run("c", "failed", { timestep_fs: 2, ensemble: "nve" }),
  run("d", "succeeded", { timestep_fs: 0.5, ensemble: "nvt" }),
  run("e", "running", { timestep_fs: 2, ensemble: "nvt" }),
  run("f", "succeeded", { ensemble: "nvt" }),
];

const RESULTS: Record<string, Record<string, unknown>> = {
  a: { energy_drift: 1.5e-4 },
  b: { energy_drift: 3.75e-5 },
  d: { energy_drift: 4e-5 },
};

describe("metricChartData", () => {
  const data = metricChartData(
    RUNS,
    { x: "timestep_fs", y: "energy_drift", by: "ensemble" },
    (id) => RESULTS[id],
  );

  it("orders the swept values and labels them with their unit", () => {
    expect(data.axis.labels).toEqual(["0.5 fs", "1 fs", "2 fs"]);
  });

  it("keeps runs with a value and failed runs, drops the rest", () => {
    expect(data.rows.map((row) => row.key).sort()).toEqual(["a", "b", "c", "d"]);
    expect(data.withValue).toBe(3);
  });

  it("puts a failed run at its x, at the top of the axis", () => {
    const failed = data.rows.find((row) => row.key === "c");
    expect(failed).toMatchObject({ failed: true, y: null, xOrder: 2, tip: "c · failed" });
    expect(failed?.plotY).toBe(data.axis.domain[1]);
  });

  it("names one series per `by` value, at its last point", () => {
    expect(data.rows.find((row) => row.key === "a")).toMatchObject({ series: "nve", label: "nve" });
    expect(data.rows.find((row) => row.key === "b")?.label).toBeNull();
    expect(data.rows.find((row) => row.key === "d")).toMatchObject({ series: "nvt", label: "nvt" });
  });

  it("reads y from a parameter when it is one", () => {
    const byParam = metricChartData(RUNS, { x: "timestep_fs", y: "timestep_fs" }, () => null);
    expect(byParam.withValue).toBe(4);
    expect(byParam.rows.every((row) => row.series === "all runs" && row.label === null)).toBe(true);
  });

  it("reports no values when no run has y", () => {
    const none = metricChartData(RUNS, { x: "timestep_fs", y: "missing" }, () => null);
    expect(none.withValue).toBe(0);
    expect(none.axis.domain).toEqual([0, 1]);
  });
});

describe("metricSpec", () => {
  // Vega needs resolved colours; these stand in for the theme's.
  const swatch = "transparent";
  const palette: OverviewPalette = {
    status: {
      running: swatch,
      queued: swatch,
      interrupted: swatch,
      succeeded: swatch,
      failed: "currentColor",
      cancelled: swatch,
    },
    accent: swatch,
    ink: swatch,
    muted: swatch,
    rule: swatch,
    ground: swatch,
    font: "sans-serif",
  };

  it("adds the failure layer to the sweep spec and compiles", async () => {
    const data = metricChartData(
      RUNS,
      { x: "timestep_fs", y: "energy_drift", by: "ensemble" },
      (id) => RESULTS[id],
    );
    const spec = metricSpec(palette, data.axis) as { layer: { mark: { shape?: string } }[] };
    expect(spec.layer.at(-1)?.mark.shape).toBe("cross");
    const compiled = await compileVegaLite(metricSpec(palette, data.axis));
    expect(compiled.marks?.length).toBeGreaterThan(0);
  });
});
