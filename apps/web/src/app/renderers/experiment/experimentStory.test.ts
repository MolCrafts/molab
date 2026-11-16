import { describe, expect, it } from "@rstest/core";
import {
  declaredCellCount,
  experimentVerdict,
  missingCellCount,
  outcomeByParameter,
  type StoryRun,
} from "./experimentStory";

const run = (
  id: string,
  status: string,
  parameters: Record<string, unknown>,
  errorMessage: string | null = null,
): StoryRun => ({ id, status, parameters, errorMessage });

const nve: StoryRun[] = [
  run("a", "succeeded", { timestep_fs: 0.5, driver: "ase" }),
  run("b", "succeeded", { timestep_fs: 1, driver: "ase" }),
  run("c", "failed", { timestep_fs: 2, driver: "ase" }, "Energy drift exceeded the tolerance"),
  run("d", "interrupted", { timestep_fs: 2, driver: "lib_md3" }, "Worker heartbeat expired"),
  run("e", "finalizing", { timestep_fs: 2, driver: "lib_md3" }),
  run("f", "succeeded", { timestep_fs: 0.5, driver: "lib_md3" }),
];

describe("experimentVerdict", () => {
  it("leads with the runs that need attention and names what they share", () => {
    const verdict = experimentVerdict(nve);
    expect(verdict.state).toBe("attention");
    expect(verdict.word).toBe("Failed");
    expect(verdict.subject).toBe("1 failed · 1 interrupted of 6 runs");
    expect(verdict.aside).toBe("1 active");
    expect(verdict.evidence).toBe(
      "Both at timestep_fs = 2 fs · Energy drift exceeded the tolerance · Worker heartbeat expired",
    );
    expect(verdict.subjectFilter).toBe("status:failed,interrupted");
    expect(verdict.attention).toEqual(["c", "d"]);
  });

  it("says what is running when nothing needs attention", () => {
    const verdict = experimentVerdict([
      run("a", "running", {}),
      run("b", "queued", {}),
      run("c", "succeeded", {}),
    ]);
    expect(verdict.word).toBe("Running");
    expect(verdict.subject).toBe("1 running · 1 queued of 3 runs");
    expect(verdict.aside).toBe("1 done");
  });

  it("says all succeeded, planned and empty in the experiment's own words", () => {
    expect(experimentVerdict([run("a", "succeeded", {}), run("b", "succeeded", {})]).subject).toBe(
      "all 2 runs",
    );
    expect(experimentVerdict([run("a", "pending", {})]).word).toBe("Planned");
    expect(experimentVerdict([], { declaredCells: 12 }).subject).toBe("12 runs declared");
    expect(experimentVerdict([]).word).toBe("Empty");
  });
});

describe("outcomeByParameter", () => {
  it("counts each run's latest status per value, in value order", () => {
    const groups = outcomeByParameter(nve, "timestep_fs");
    expect(groups.map((group) => group.label)).toEqual(["0.5 fs", "1 fs", "2 fs"]);
    expect(groups[2]?.counts).toMatchObject({ total: 3, failed: 1, interrupted: 1, running: 1 });
  });
});

describe("declaredCellCount", () => {
  it("multiplies the declared lists and ignores scalars", () => {
    expect(declaredCellCount({ a: [1, 2, 3], b: ["x", "y"], c: 5 })).toBe(6);
    expect(declaredCellCount({})).toBe(0);
  });
});

describe("missingCellCount", () => {
  it("counts declared combinations no run has used", () => {
    const space = { timestep_fs: [0.5, 1, 2, 4], driver: ["ase", "lib_md3"] };
    expect(missingCellCount(space, nve)).toBe(8 - 5);
    expect(missingCellCount({}, nve)).toBe(0);
  });
});

describe("outcomeByParameter · unset", () => {
  it("files a run that never set the parameter apart, after the values", () => {
    const groups = outcomeByParameter(
      [...nve, run("g", "succeeded", { driver: "ase" })],
      "timestep_fs",
    );
    expect(groups.at(-1)?.label).toBe("timestep_fs unset");
    expect(groups.at(-1)?.counts.total).toBe(1);
  });
});
