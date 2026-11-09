import { describe, expect, it } from "@rstest/core";
import { formatParameter, parameterUnit, runLabel, runTitles, withRunTitles } from "./runTitle";

const run = (id: string, parameters: Record<string, unknown>, experimentId = "x") => ({
  id,
  name: `name-${id}`,
  experimentId,
  parameters,
});

describe("run titles", () => {
  it("names a run by the values that vary in its experiment, keys in order", () => {
    const titles = runTitles([
      run("a", { timestep_fs: 2, driver: "ase", ensemble: "nve", steps: 500000 }),
      run("b", { timestep_fs: 1, driver: "ase", ensemble: "nvt", steps: 500000 }),
      run("c", { timestep_fs: 2, driver: "lib_md3", ensemble: "nve", steps: 500000 }),
    ]);
    expect(titles.get("a")).toBe("ase · nve · 2 fs");
    expect(titles.get("b")).toBe("ase · nvt · 1 fs");
  });

  it("reads a unit from the key suffix and keeps the key on a bare number", () => {
    expect(parameterUnit("timestep_fs")).toBe("fs");
    expect(parameterUnit("temperature_K")).toBe("K");
    expect(parameterUnit("top_k")).toBeNull();
    expect(formatParameter("timestep_fs", 0.5)).toBe("0.5 fs");
    expect(formatParameter("seed", 42)).toBe("seed 42");
    expect(formatParameter("lr", 0.0001)).toBe("lr 1e-4");
    expect(formatParameter("driver", "ase")).toBe("ase");
    expect(formatParameter("thermostat", true)).toBe("thermostat");
  });

  it("titles each experiment on its own and falls back to the name when nothing varies", () => {
    const titles = runTitles([
      run("a", { seed: 1 }, "one"),
      run("b", { seed: 2 }, "one"),
      run("c", { seed: 1 }, "two"),
    ]);
    expect(titles.get("a")).toBe("seed 1");
    expect(titles.get("c")).toBe("name-c");
  });

  it("stamps titles without changing the input and labels a run by them", () => {
    const input = [run("a", { seed: 1 }), run("b", { seed: 2 })];
    const titled = withRunTitles(input);
    expect(titled[0]?.title).toBe("seed 1");
    expect("title" in (input[0] as object)).toBe(false);
    expect(runLabel({ id: "r", name: "", title: "" })).toBe("r");
  });
});
