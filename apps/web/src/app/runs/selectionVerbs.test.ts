import { describe, expect, it } from "@rstest/core";
import type { RunSummary } from "@/app/types";
import { planSelection } from "./selectionVerbs";

const run = (status: string, executionId?: string): RunSummary =>
  ({
    id: executionId ? `run-${executionId}` : `run-${status}`,
    name: status,
    path: "projects/p/experiments/e/runs/run",
    status,
    summary: "",
    updatedAt: "",
    projectId: "p",
    experimentId: "e",
    definitionHash: "def",
    experimentRevisionId: "rev",
    statusSummary: { total: 0, active: 0, notStarted: true, byStatus: {} },
    parameters: {},
    workflowSource: null,
    workflowSnapshot: null,
    startedAt: null,
    finishedAt: null,
    executionHistory: executionId
      ? [
          {
            executionId,
            mode: "initial",
            createdAt: "",
            startedAt: null,
            finishedAt: null,
            status,
            basedOnExecutionId: null,
            executor: {},
            environment: {},
            error: null,
          },
        ]
      : [],
    errorMessage: null,
  }) as RunSummary;

describe("planSelection", () => {
  it("sorts a mixed selection into start, cancel, resume, and rerun", () => {
    const plan = planSelection([
      run("pending"),
      run("running", "e01"),
      run("failed", "e02"),
      run("succeeded", "e03"),
    ]);
    expect(plan.start.map((item) => item.mode)).toEqual(["initial"]);
    expect(plan.cancel.map((item) => item.executionId)).toEqual(["e01"]);
    expect(plan.resume.map((item) => item.executionId)).toEqual(["e02"]);
    expect(plan.rerun.map((item) => item.executionId)).toEqual(["e02", "e03"]);
  });

  it("does not start a pending run that already has an attempt", () => {
    const plan = planSelection([run("pending", "e01")]);
    expect(plan.start).toEqual([]);
  });
});
