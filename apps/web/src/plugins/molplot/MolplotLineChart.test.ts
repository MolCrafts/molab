/**
 * The line chart's incremental update plan and its structure key: a live run
 * appends points without re-mounting the Vega container.
 */

import type { LineChartConfig } from "@molcrafts/molplot";
import { describe, expect, it } from "@rstest/core";
import { lineChartStructureKey, planSeriesUpdate } from "./MolplotLineChart";

const configOf = (points: { x: number; y: number }[]): LineChartConfig => ({
  series: [{ id: "train/loss", label: "train/loss", color: "var(--x)", initialPoints: points }],
  xAxis: { label: "step", type: "linear" },
  yAxis: { label: "train/loss", type: "linear" },
});

describe("lineChartStructureKey", () => {
  it("stays stable when only points change", () => {
    const a = configOf([{ x: 0, y: 1 }]);
    const b = configOf([
      { x: 0, y: 1 },
      { x: 1, y: 0.7 },
    ]);
    expect(lineChartStructureKey(a)).toBe(lineChartStructureKey(b));
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
