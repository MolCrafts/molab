import { describe, expect, it } from "@rstest/core";
import {
  formatCell,
  formatWhere,
  matchesWhere,
  parseColumns,
  parseLimit,
  parseWhere,
  runValue,
} from "./runQuery";

describe("parseWhere", () => {
  it("reads a single clause", () => {
    expect(parseWhere("timestep_fs>=0.5")).toEqual({
      conditions: [{ key: "timestep_fs", op: ">=", value: "0.5" }],
      invalid: [],
    });
  });

  it("reads a conjunction with any separator and every operator", () => {
    const parsed = parseWhere('a=1 && b != "nve", c<2 and d<=3 & e>4,f>=5,g==x');
    expect(parsed.invalid).toEqual([]);
    expect(parsed.conditions.map(({ key, op, value }) => `${key}${op}${value}`)).toEqual([
      "a=1",
      "b!=nve",
      "c<2",
      "d<=3",
      "e>4",
      "f>=5",
      "g=x",
    ]);
  });

  it("keeps a clause it cannot read as invalid", () => {
    expect(parseWhere("a>1, nonsense").invalid).toEqual(["nonsense"]);
  });

  it("reads nothing from an empty or missing filter", () => {
    expect(parseWhere(undefined)).toEqual({ conditions: [], invalid: [] });
    expect(parseWhere("  ")).toEqual({ conditions: [], invalid: [] });
  });
});

describe("matchesWhere", () => {
  const values: Record<string, unknown> = { timestep_fs: 1, driver: "ase", drift: 1.5e-4 };
  const lookup = (key: string): unknown => values[key];

  it("compares numbers as numbers", () => {
    expect(matchesWhere(parseWhere("timestep_fs>=0.5").conditions, lookup)).toBe(true);
    expect(matchesWhere(parseWhere("timestep_fs>1").conditions, lookup)).toBe(false);
    expect(matchesWhere(parseWhere("drift<1e-3").conditions, lookup)).toBe(true);
    expect(matchesWhere(parseWhere("timestep_fs=1.0").conditions, lookup)).toBe(true);
  });

  it("compares words by equality only", () => {
    expect(matchesWhere(parseWhere("driver=ase").conditions, lookup)).toBe(true);
    expect(matchesWhere(parseWhere("driver!=ase").conditions, lookup)).toBe(false);
    expect(matchesWhere(parseWhere("driver>a").conditions, lookup)).toBe(false);
  });

  it("fails a condition on a missing key, and passes with no conditions", () => {
    expect(matchesWhere(parseWhere("seed=1").conditions, lookup)).toBe(false);
    expect(matchesWhere([], lookup)).toBe(true);
  });
});

describe("formatWhere", () => {
  it("echoes the filter with readable signs", () => {
    expect(formatWhere(parseWhere("timestep_fs>=0.5, driver!=x").conditions)).toBe(
      "timestep_fs ≥ 0.5 · driver ≠ x",
    );
  });
});

describe("columns and limit", () => {
  it("splits and trims columns", () => {
    expect(parseColumns(" timestep_fs, energy_drift ,,")).toEqual(["timestep_fs", "energy_drift"]);
    expect(parseColumns(undefined)).toEqual([]);
  });

  it("accepts only a positive integer limit", () => {
    expect(parseLimit("5")).toBe(5);
    expect(parseLimit("0")).toBeNull();
    expect(parseLimit("x")).toBeNull();
    expect(parseLimit(undefined)).toBeNull();
  });
});

describe("formatCell", () => {
  it("prints numbers compactly and marks them numeric", () => {
    expect(formatCell(2)).toEqual({ text: "2", numeric: true });
    expect(formatCell(0.5)).toEqual({ text: "0.5", numeric: true });
    expect(formatCell(3.75e-5)).toEqual({ text: "3.75e-5", numeric: true });
    expect(formatCell(1.5e-4)).toEqual({ text: "1.50e-4", numeric: true });
    expect(formatCell(2_500_000)).toEqual({ text: "2.50e+6", numeric: true });
  });

  it("prints a missing value as a dash and anything else as text", () => {
    expect(formatCell(undefined)).toEqual({ text: "—", numeric: false });
    expect(formatCell(null)).toEqual({ text: "—", numeric: false });
    expect(formatCell("nve")).toEqual({ text: "nve", numeric: false });
    expect(formatCell(true)).toEqual({ text: "true", numeric: false });
    expect(formatCell([1, 2])).toEqual({ text: "[1,2]", numeric: false });
    expect(formatCell(Number.NaN)).toEqual({ text: "—", numeric: false });
  });
});

describe("runValue", () => {
  it("prefers a parameter, then a result", () => {
    expect(runValue({ a: 1 }, { a: 2, b: 3 }, "a")).toBe(1);
    expect(runValue({ a: 1 }, { b: 3 }, "b")).toBe(3);
    expect(runValue({ a: 1 }, null, "b")).toBeUndefined();
  });
});
