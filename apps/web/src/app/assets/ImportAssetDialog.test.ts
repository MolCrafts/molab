import { describe, expect, it } from "@rstest/core";
import { importPathProblem } from "./ImportAssetDialog";

describe("importPathProblem", () => {
  it("accepts a path inside the workspace", () => {
    expect(importPathProblem("data/ligands.csv")).toBeNull();
    expect(importPathProblem("")).toBeNull();
  });

  it("refuses an absolute path and one that leaves the workspace", () => {
    expect(importPathProblem("/etc/passwd")).toMatch(/leading/);
    expect(importPathProblem("data/../../x")).toMatch(/leave/);
  });
});
