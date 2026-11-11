import { describe, expect, it } from "@rstest/core";
import { selectionOfTarget } from "./Preview";

describe("selectionOfTarget", () => {
  it("hands a plugin section the selection it already understands", () => {
    expect(
      selectionOfTarget({
        kind: "attempt",
        runId: "r",
        projectId: "p",
        experimentId: "e",
        executionId: "e01",
      }),
    ).toEqual({ objectType: "run", objectId: "r" });
    expect(
      selectionOfTarget({ kind: "node", projectId: "p", experimentId: "e", taskId: "t" }),
    ).toEqual({
      objectType: "task",
      objectId: "t",
      taskId: "t",
      runId: "",
    });
    expect(selectionOfTarget({ kind: "knowledge", path: "a/b.md" })).toEqual({
      objectType: "knowledge",
      objectId: "a/b.md",
    });
  });
});
