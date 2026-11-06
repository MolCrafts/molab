import { describe, expect, it } from "@rstest/core";
import { axisDraft, compileSweep, draftsFromParameterSpace, parseAxisValues } from "./grid";

describe("compileSweep", () => {
  it("builds the cartesian product of named axes", () => {
    const compiled = compileSweep([
      axisDraft("a", "lr", "0.1, 0.2"),
      axisDraft("b", "batch", "16 32"),
    ]);
    expect(compiled).toEqual({
      grid: { axes: { lr: [0.1, 0.2], batch: [16, 32] }, cells: 4 },
    });
  });

  it("keeps a non-numeric token as text", () => {
    expect(parseAxisValues("fast, 1")).toEqual(["fast", 1]);
  });

  it("rejects a nameless axis, a duplicate, and an empty value list", () => {
    expect(compileSweep([axisDraft("a", "", "1, 2")])).toEqual({
      error: "Every axis needs a name.",
    });
    expect(compileSweep([axisDraft("a", "lr", "1"), axisDraft("b", "lr", "2")])).toEqual({
      error: "Axis “lr” is listed twice.",
    });
    expect(compileSweep([axisDraft("a", "lr", "  ")])).toEqual({
      error: "Axis “lr” needs a value.",
    });
  });

  it("reads list axes from a parameter space and ignores scalars", () => {
    expect(draftsFromParameterSpace({ lr: [0.1, 0.2], note: "fixed" })).toEqual([
      axisDraft("axis-0", "lr", "0.1, 0.2"),
    ]);
    expect(draftsFromParameterSpace({})).toEqual([axisDraft("axis-0")]);
  });
});
