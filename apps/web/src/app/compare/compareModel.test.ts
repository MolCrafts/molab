import { describe, expect, it } from "@rstest/core";
import { parameterRows, resultRows } from "./compareModel";

const columns = [
  {
    key: "a",
    parameters: { driver: "ase", timestep_fs: 0.5, steps: 500 },
    results: { energy_drift: 3.75e-5, frames: 51 },
    seconds: 1200,
  },
  {
    key: "b",
    parameters: { driver: "ase", timestep_fs: 1, steps: 500 },
    results: { energy_drift: 1.5e-4, frames: 51 },
    seconds: 2100,
  },
  {
    key: "c",
    parameters: { driver: "ase", timestep_fs: 2, steps: 500 },
    results: null,
    seconds: 3480,
  },
];

describe("compare model", () => {
  it("lists varying parameters first and marks values that differ from the baseline", () => {
    const rows = parameterRows(columns);
    expect(rows.map((row) => [row.key, row.identical])).toEqual([
      ["timestep_fs", false],
      ["driver", true],
      ["steps", true],
    ]);
    expect(rows[0]?.values).toEqual(["0.5 fs", "1 fs", "2 fs"]);
    expect(rows[0]?.differs).toEqual([false, true, true]);
  });

  it("reads differences against whichever column is the baseline", () => {
    expect(parameterRows(columns, 1)[0]?.differs).toEqual([true, false, true]);
  });

  it("lists results with a dash where a run has none, then time", () => {
    const rows = resultRows(columns);
    expect(rows.map((row) => row.key)).toEqual(["energy_drift", "frames", "time"]);
    expect(rows[0]?.values).toEqual(["3.75e-5", "1.50e-4", "—"]);
    expect(rows[0]?.differs).toEqual([false, true, false]);
    expect(rows[2]?.values).toEqual(["20m", "35m", "58m"]);
  });
});
