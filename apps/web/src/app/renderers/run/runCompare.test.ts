import { describe, expect, it } from "@rstest/core";
import { baselineOf, type ComparedRun, keyMetric, parameterRows, sweepOf } from "./runCompare";

const run = (
  id: string,
  parameters: Record<string, unknown>,
  status = "succeeded",
  results: Record<string, unknown> | null = { energy_drift: 0.001, frames: 51 },
): ComparedRun => ({ id, title: id, parameters, status, results });

const sweep = [
  run("a", { timestep_fs: 0.5, driver: "ase" }, "succeeded", { energy_drift: 1e-5 }),
  run("b", { timestep_fs: 1, driver: "ase" }, "succeeded", { energy_drift: 4e-5 }),
  run("c", { timestep_fs: 2, driver: "ase" }, "failed", null),
  run("d", { timestep_fs: 2, driver: "lib_md3" }, "succeeded", { energy_drift: 3e-4 }),
];

describe("keyMetric", () => {
  it("takes the run's own first number, else what most siblings report", () => {
    expect(keyMetric(sweep[0] as ComparedRun, [])).toBe("energy_drift");
    expect(keyMetric(sweep[2] as ComparedRun, sweep)).toBe("energy_drift");
    expect(keyMetric({ results: null }, [])).toBeNull();
  });
});

describe("sweepOf", () => {
  it("puts the run on the numeric swept axis, other values naming the lines", () => {
    const self = sweep[2] as ComparedRun;
    const result = sweepOf(self, sweep, "energy_drift");
    expect(result?.axisKey).toBe("timestep_fs");
    expect(result?.selfSeries).toBe("ase");
    const mine = result?.points.find((point) => point.self);
    expect(mine).toMatchObject({ x: "2 fs", xOrder: 2, y: null, status: "failed" });
    expect(result?.siblingsWithResult).toBe(3);
  });

  it("draws nothing when nothing varies or no sibling has the result", () => {
    expect(sweepOf(run("x", { a: 1 }), [run("y", { a: 1 })], "energy_drift")).toBeNull();
    expect(
      sweepOf(run("x", { a: 1 }), [run("y", { a: 2 }, "failed", null)], "energy_drift"),
    ).toBeNull();
  });
});

describe("baseline and parameter rows", () => {
  it("reads a run against its nearest successful sibling", () => {
    const self = run("c", { timestep_fs: 2, driver: "ase", steps: 500000 }, "failed");
    const siblings = [
      run("a", { timestep_fs: 1, driver: "ase", steps: 500000 }),
      run("d", { timestep_fs: 2, driver: "lib_md3", steps: 500000 }, "failed"),
      run("e", { timestep_fs: 0.5, driver: "lib_md3", steps: 500000 }),
    ];
    const baseline = baselineOf(self, siblings);
    expect(baseline?.id).toBe("a");
    expect(parameterRows(self, siblings, baseline)).toEqual([
      { key: "driver", value: "ase", role: "swept", differs: false },
      { key: "timestep_fs", value: "2 fs", role: "swept", differs: true },
      { key: "steps", value: "500 000", role: "fixed", differs: false },
    ]);
  });
});
