import { describe, expect, it } from "@rstest/core";
import { DOC_SKELETON, isSourcedClass, runsForHost } from "./docTemplates";

describe("DOC_SKELETON", () => {
  it("gives a sourced class a section skeleton and leaves Note empty", () => {
    expect(DOC_SKELETON.Note).toBe("");
    expect(DOC_SKELETON.Finding).toContain("## Result");
    expect(DOC_SKELETON.Plan).toContain("## Objective");
    expect(isSourcedClass("Finding")).toBe(true);
    expect(isSourcedClass("Note")).toBe(false);
    expect(isSourcedClass("Literature")).toBe(false);
  });
});

describe("runsForHost", () => {
  const runs = [
    { id: "r1", name: "cool", path: "projects/p/experiments/e/runs/cool", ref: "molab:run/r1" },
    { id: "r2", name: "heat", path: "projects/p/experiments/other/runs/heat", ref: "molab:run/r2" },
    { id: "r3", name: "bare", path: "projects/p/experiments/e/runs/bare" },
  ];

  it("keeps runs under the host and drops a run with no ref", () => {
    expect(runsForHost(runs, "projects/p/experiments/e").map((run) => run.id)).toEqual(["r1"]);
  });

  it("returns every referenced run when the host is the workspace root", () => {
    expect(runsForHost(runs, "").map((run) => run.id)).toEqual(["r1", "r2"]);
  });
});
