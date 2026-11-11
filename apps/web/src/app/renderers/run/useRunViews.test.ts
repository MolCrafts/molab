import type { RunViewContribution } from "@molcrafts/molab-plugin";
import { describe, expect, it } from "@rstest/core";
import type { ExecutionRecordSummary } from "@/app/types";
import { attemptWord } from "./RunAttemptChip";
import { applicableRunViews } from "./useRunViews";

const view = (id: string, patterns?: string[]): RunViewContribution => ({
  id,
  label: id,
  ...(patterns ? { files: { patterns } } : {}),
  Component: () => null,
});
const file = (relPath: string) => ({
  name: relPath.split("/").pop() ?? relPath,
  relPath,
  type: "file",
});

describe("applicableRunViews", () => {
  it("keeps a view with no matcher and a view whose files the attempt has, with its files", () => {
    const views = applicableRunViews(
      [view("always"), view("plot", ["log.lammps", "**/*.mlp.jsonl"]), view("vis", ["*.xyz"])],
      [file("log.lammps"), file("out/metrics.mlp.jsonl"), file("run.log")],
    );
    expect(views.map((v) => [v.contribution.id, v.files.map((f) => f.relPath)])).toEqual([
      ["always", []],
      ["plot", ["log.lammps", "out/metrics.mlp.jsonl"]],
    ]);
  });
});

describe("attemptWord", () => {
  const attempt = (executionId: string, status: string): ExecutionRecordSummary =>
    ({
      executionId,
      status,
      mode: "initial",
      createdAt: "",
      startedAt: null,
      finishedAt: null,
      basedOnExecutionId: null,
      executor: {},
      environment: {},
      error: null,
    }) as ExecutionRecordSummary;
  const history = [
    attempt("e01", "succeeded"),
    attempt("e02", "failed"),
    attempt("e03", "running"),
  ];

  it("names the latest and the run result (the latest success)", () => {
    expect(attemptWord(history, "e03")).toBe("latest");
    expect(attemptWord(history, "e02")).toBe("");
    expect(attemptWord(history, "e01")).toBe("run result");
    expect(attemptWord([attempt("e01", "succeeded")], "e01")).toBe("latest · run result");
  });
});
