/**
 * The comparison matrix — the presentation for runs that record one number per
 * measurement rather than a curve.
 */

import { describe, expect, it } from "@rstest/core";
import type { RunAllSeries } from "@/plugins/molplot";
import type { ScalarSeries } from "@/plugins/molplot/RunMetricsView";
import { metricRows, parameterRows } from "./CompareTable";
import type { CompareEntry } from "./types";
import { refKey } from "./types";

const entry = (run: string, parameters: Record<string, unknown> = {}): CompareEntry => ({
  ref: { workspaceKey: "w", projectId: "p", experimentId: "e", runId: run },
  selected: true,
  executionId: null,
  workspaceLabel: "w",
  projectName: "p",
  experimentName: "e",
  runName: run,
  parameters,
  addedAt: "2026-09-06T00:00:00Z",
});

/** A one-off scalar, the shape lab-v3's benchmark runs actually record. */
const oneOff = (key: string, value: number): ScalarSeries => ({
  key,
  group: "",
  points: [{ step: 0, wall: 0, y: value }],
  latest: value,
});

const curve = (key: string, ys: number[]): ScalarSeries => ({
  key,
  group: "",
  points: ys.map((y, i) => ({ step: i, wall: i, y })),
  latest: ys[ys.length - 1],
});

const runRow = (run: string, series: ScalarSeries[]): RunAllSeries => ({
  key: refKey(entry(run).ref),
  label: run,
  title: run,
  series,
});

describe("parameterRows", () => {
  it("marks rows that differ and leaves identical ones unmarked", () => {
    const rows = parameterRows([
      entry("a", { engine: "molnex", n: 200 }),
      entry("b", { engine: "official", n: 200 }),
    ]);
    expect(rows.map((r) => [r.key, r.varies])).toEqual([
      ["engine", true],
      ["n", false],
    ]);
  });

  it("fills a run missing a parameter with a dash rather than dropping the row", () => {
    const rows = parameterRows([entry("a", { block: 4096 }), entry("b", {})]);
    expect(rows[0].values).toEqual(["4.096e+3", "—"]);
  });

  it("needs no metrics scan", () => {
    expect(parameterRows([entry("a", { seed: 1 })])).toHaveLength(1);
  });
});

describe("metricRows", () => {
  const columns = ["a", "b"].map((r) => refKey(entry(r).ref));

  it("puts one-off scalars in the matrix, one column per run", () => {
    const rows = metricRows(
      [
        runRow("a", [oneOff("n_atoms", 3200), oneOff("eager_e_seconds", 0.42)]),
        runRow("b", [oneOff("n_atoms", 3200), oneOff("eager_e_seconds", 0.51)]),
      ],
      columns,
    );
    expect(rows.map((r) => r.key)).toEqual(["eager_e_seconds", "n_atoms"]);
    expect(rows.find((r) => r.key === "n_atoms")?.varies).toBe(false);
    expect(rows.find((r) => r.key === "eager_e_seconds")?.varies).toBe(true);
  });

  it("shows a dash where a run never logged that metric", () => {
    const rows = metricRows(
      [runRow("a", [oneOff("nograd_e_seconds", 1.5)]), runRow("b", [oneOff("n_atoms", 10)])],
      columns,
    );
    expect(rows.find((r) => r.key === "nograd_e_seconds")?.values).toEqual(["1.500", "—"]);
  });

  it("reports a series by its last value, and says how many points it had", () => {
    const rows = metricRows([runRow("a", [curve("loss", [9, 5, 2])])], [columns[0]]);
    expect(rows[0].values).toEqual(["2.000"]);
    expect(rows[0].counts).toEqual([3]);
  });

  it("keeps a one-off scalar's count at 1, so it is not read as a series", () => {
    const rows = metricRows([runRow("a", [oneOff("n_atoms", 10)])], [columns[0]]);
    expect(rows[0].counts).toEqual([1]);
  });

  it("follows the caller's column order, not the load order", () => {
    const rows = metricRows(
      [runRow("b", [oneOff("x", 2)]), runRow("a", [oneOff("x", 1)])],
      columns,
    );
    expect(rows[0].values).toEqual(["1.000", "2.000"]);
  });

  it("is empty when nothing has been scanned yet", () => {
    expect(metricRows([], columns)).toEqual([]);
  });
});
