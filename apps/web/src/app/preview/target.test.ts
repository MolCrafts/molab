import { describe, expect, it } from "@rstest/core";
import { type PreviewTarget, previewKey, previewPath } from "./target";

const run: PreviewTarget = { kind: "run", runId: "md-009", projectId: "nve", experimentId: "exp" };

describe("previewKey", () => {
  it("names what is previewed, so the same thing twice is one Preview", () => {
    expect(previewKey(run)).toBe("run:md-009");
    expect(previewKey({ ...run, label: "ase · nve · 2 fs" })).toBe(previewKey(run));
  });

  it("scopes a task and an attempt by their run, a node by its experiment", () => {
    expect(
      previewKey({ kind: "task", runId: "r", projectId: "p", experimentId: "e", taskId: "t" }),
    ).toBe("task:r/t");
    expect(
      previewKey({
        kind: "attempt",
        runId: "r",
        projectId: "p",
        experimentId: "e",
        executionId: "e01",
      }),
    ).toBe("attempt:r/e01");
    expect(previewKey({ kind: "node", projectId: "p", experimentId: "e", taskId: "t" })).toBe(
      "node:e/t",
    );
  });
});

describe("previewPath", () => {
  it("opens a run, an attempt and a task at their own pages", () => {
    expect(previewPath(run)).toBe("/projects/nve/experiments/exp/runs/md-009");
    expect(
      previewPath({
        kind: "attempt",
        runId: "md-009",
        projectId: "nve",
        experimentId: "exp",
        executionId: "e01",
      }),
    ).toBe("/projects/nve/experiments/exp/runs/md-009?tab=executions&attempt=e01");
    expect(
      previewPath({
        kind: "task",
        runId: "md-009",
        projectId: "nve",
        experimentId: "exp",
        taskId: "simulate",
      }),
    ).toBe("/projects/nve/experiments/exp/runs/md-009/tasks/simulate");
  });

  it("opens a definition node in the experiment's Workflow view", () => {
    expect(
      previewPath({ kind: "node", projectId: "nve", experimentId: "exp", taskId: "simulate" }),
    ).toBe("/projects/nve/experiments/exp/workflow");
  });

  it("opens containers, assets, files and documents", () => {
    expect(previewPath({ kind: "experiment", projectId: "nve", experimentId: "exp" })).toBe(
      "/projects/nve/experiments/exp",
    );
    expect(previewPath({ kind: "project", projectId: "nve" })).toBe("/projects/nve");
    expect(previewPath({ kind: "asset", assetId: "a 1" })).toBe("/assets/a%201");
    expect(previewPath({ kind: "file", filePath: "a/workflow.py", fileKind: "python" })).toBe(
      "/workspace?file=a%2Fworkflow.py&fileKind=python",
    );
    expect(previewPath({ kind: "knowledge", path: "nve/knowledges/limit.md" })).toBe(
      "/knowledge/nve/knowledges/limit.md",
    );
  });
});
