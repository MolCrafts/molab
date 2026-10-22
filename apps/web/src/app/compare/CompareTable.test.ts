/**
 * The comparison matrix — the presentation for runs that record one number per
 * measurement rather than a curve.
 */

import { describe, expect, it } from "@rstest/core";
import type { RunAllSeries } from "@/plugins/molplot";
import type { ScalarSeries } from "@/plugins/molplot/RunMetricsView";
import type { MatrixRow } from "./CompareTable";
import {
  clampWidth,
  compileRunFilter,
  groupedEntries,
  metricRows,
  nextRunSort,
  parameterRows,
  rowExtrema,
  rowGroups,
  sliceMeasure,
  sortEntries,
  visibleRows,
} from "./CompareTable";
import type { CompareEntry } from "./types";
import { refKey } from "./types";

const entry = (run: string, parameters: Record<string, unknown> = {}): CompareEntry => ({
  ref: { workspaceKey: "w", projectId: "p", experimentId: "e", runId: run },
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

describe("visibleRows", () => {
  const rows: MatrixRow[] = [
    {
      key: "same",
      kind: "parameter",
      values: ["1", "1"],
      numeric: [1, 1],
      varies: false,
      counts: [1, 1],
    },
    {
      key: "diff",
      kind: "parameter",
      values: ["1", "2"],
      numeric: [1, 2],
      varies: true,
      counts: [1, 1],
    },
  ];

  it("keeps only rows that differ", () => {
    expect(visibleRows(rows, false).map((row) => row.key)).toEqual(["diff"]);
  });

  it("shows every row when asked", () => {
    expect(visibleRows(rows, true).map((row) => row.key)).toEqual(["same", "diff"]);
  });

  it("falls back to every row when nothing differs", () => {
    expect(visibleRows([rows[0]], false)).toEqual([rows[0]]);
  });
});

describe("groupedEntries", () => {
  it("pulls runs of one experiment together without losing within-experiment order", () => {
    const a = entry("a");
    const b = {
      ...entry("b"),
      experimentName: "other",
      ref: { ...entry("b").ref, experimentId: "other" },
    };
    const c = entry("c");
    expect(groupedEntries([a, b, c]).map((item) => item.runName)).toEqual(["a", "c", "b"]);
  });
});

describe("rowGroups", () => {
  it("is one group when every run shares an experiment", () => {
    expect(rowGroups([entry("a"), entry("b")])).toEqual([
      { key: expect.any(String), label: "e", count: 2 },
    ]);
  });

  it("names the project when more than one project is present", () => {
    const other = {
      ...entry("b"),
      projectName: "q",
      experimentName: "f",
      ref: { ...entry("b").ref, projectId: "q", experimentId: "f" },
    };
    const groups = rowGroups([entry("a"), other]);
    expect(groups.map((group) => [group.label, group.count])).toEqual([
      ["p · e", 1],
      ["q · f", 1],
    ]);
  });
});

describe("compileRunFilter", () => {
  it("matches all names when empty", () => {
    const match = compileRunFilter("  ");
    expect(match("n=8")).toBe(true);
  });

  it("applies a regular expression to the run name", () => {
    const match = compileRunFilter("^n=");
    expect(match("n=8")).toBe(true);
    expect(match("seed=1")).toBe(false);
  });

  it("falls back to substring when the pattern is invalid", () => {
    const match = compileRunFilter("(");
    expect(match("a(b")).toBe(true);
    expect(match("ab")).toBe(false);
  });
});

describe("sliceMeasure", () => {
  it("keeps values in the caller index order and recomputes varies", () => {
    const sliced = sliceMeasure(
      {
        key: "n",
        kind: "parameter",
        values: ["1", "2", "1"],
        numeric: [1, 2, 1],
        varies: true,
        counts: [1, 1, 1],
      },
      [0, 2],
    );
    expect(sliced.values).toEqual(["1", "1"]);
    expect(sliced.varies).toBe(false);
  });
});

describe("rowExtrema", () => {
  it("returns min and max when they differ", () => {
    expect(rowExtrema([1, 3, 2])).toEqual({ min: 1, max: 3 });
  });

  it("is null when every number is the same or there are not enough", () => {
    expect(rowExtrema([2, 2, 2])).toBeNull();
    expect(rowExtrema([1, null])).toBeNull();
  });
});

describe("clampWidth", () => {
  it("stays inside the inclusive bounds", () => {
    expect(clampWidth(10, 48, 360)).toBe(48);
    expect(clampWidth(400, 48, 360)).toBe(360);
    expect(clampWidth(72.8, 48, 360)).toBe(73);
  });
});

describe("sortEntries", () => {
  it("cycles run → experiment → project", () => {
    expect(nextRunSort("run")).toBe("experiment");
    expect(nextRunSort("experiment")).toBe("project");
    expect(nextRunSort("project")).toBe("run");
  });

  it("orders by the chosen name first", () => {
    const a = { ...entry("z"), experimentName: "e1", projectName: "p2" };
    const b = {
      ...entry("a"),
      experimentName: "e2",
      projectName: "p1",
      ref: { ...entry("a").ref, runId: "a" },
    };
    expect(sortEntries([a, b], "run").map((row) => row.runName)).toEqual(["a", "z"]);
    expect(sortEntries([a, b], "project").map((row) => row.projectName)).toEqual(["p1", "p2"]);
  });
});
