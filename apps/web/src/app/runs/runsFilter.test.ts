import { describe, expect, it } from "@rstest/core";
import { filterRuns, parseFilter } from "./runsFilter";

const runs = [
  {
    id: "md-001",
    title: "ase · nve · 0.5 fs",
    status: "succeeded",
    parameters: { timestep_fs: 0.5, driver: "ase" },
  },
  {
    id: "md-009",
    title: "ase · nve · 2 fs",
    status: "failed",
    parameters: { timestep_fs: 2, driver: "ase" },
  },
  {
    id: "md-010",
    title: "ase · nvt · 2 fs",
    status: "interrupted",
    parameters: { timestep_fs: 2, driver: "ase" },
  },
  {
    id: "md-011",
    title: "lib_md3 · nve · 2 fs",
    status: "finalizing",
    parameters: { timestep_fs: 2, driver: "lib_md3" },
  },
];

describe("runs filter", () => {
  it("parses status, parameter, comparison and free-text terms", () => {
    expect(parseFilter("status:failed,interrupted driver:ase timestep_fs>=1 nve")).toEqual([
      { kind: "status", values: ["failed", "interrupted"] },
      { kind: "equals", key: "driver", values: ["ase"] },
      { kind: "compare", key: "timestep_fs", op: ">=", value: 1 },
      { kind: "text", value: "nve" },
    ]);
  });

  it("keeps runs that hold every term", () => {
    const ids = (text: string) => filterRuns(runs, text).map((run) => run.id);
    expect(ids("status:failed,interrupted")).toEqual(["md-009", "md-010"]);
    expect(ids("status:running")).toEqual(["md-011"]);
    expect(ids("timestep_fs>1 driver:ase")).toEqual(["md-009", "md-010"]);
    expect(ids("nve")).toEqual(["md-001", "md-009", "md-011"]);
    expect(ids("md-010")).toEqual(["md-010"]);
    expect(ids("")).toHaveLength(4);
  });
});
