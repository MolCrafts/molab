import { describe, expect, it } from "@rstest/core";

import {
  distinguishingParameters,
  resultFigures,
  runVerdict,
  siblingStanding,
  taskSpans,
  unstartedTasks,
} from "@/app/renderers/run/runStory";
import type { WorkspaceRunRow } from "@/app/runs/types";
import type { ExecutionRecordSummary, RunSummary } from "@/app/types";
import type { TaskGraphJson } from "@/plugins/workflow/task-graph-ir";

const attempt = (status: string, mode = "initial"): ExecutionRecordSummary => ({
  executionId: "e01",
  mode,
  createdAt: "2026-03-01T12:00:00Z",
  startedAt: "2026-03-01T12:00:00Z",
  finishedAt: status === "running" ? null : "2026-03-01T12:48:00Z",
  status,
  basedOnExecutionId: null,
  executor: {},
  environment: {},
  error: status === "failed" ? { type: "RuntimeError", message: "CUDA out of memory" } : null,
});

const runOf = (history: ExecutionRecordSummary[]): RunSummary =>
  ({
    id: "run-b",
    name: "b",
    executionHistory: history,
    errorMessage: null,
    parameters: { lr: 0.002, seed: 1 },
  }) as unknown as RunSummary;

const graph: TaskGraphJson = {
  task_configs: [
    {
      id: "prepare",
      type: "dataset.prepare",
      label: "Prepare",
      status: "completed",
      startedAt: "2026-03-01T12:00:00Z",
      finishedAt: "2026-03-01T12:06:00Z",
    },
    {
      id: "train",
      type: "model.train",
      label: "Train model",
      status: "failed",
      startedAt: "2026-03-01T12:06:00Z",
      finishedAt: "2026-03-01T12:48:00Z",
      error: "RuntimeError: CUDA out of memory",
    },
    { id: "evaluate", type: "metrics.evaluate", status: "skipped" },
  ],
  links: [],
};

const sibling = (id: string, minutes: number, parameters: Record<string, unknown>) =>
  ({
    id,
    name: id,
    parameters,
    statusSummary: { total: 1, active: 0, notStarted: false, byStatus: { succeeded: 1 } },
    executions: [
      {
        executionId: "e01",
        status: "succeeded",
        createdAt: "2026-03-01T12:00:00Z",
        startedAt: "2026-03-01T12:00:00Z",
        finishedAt: new Date(Date.parse("2026-03-01T12:00:00Z") + minutes * 60_000).toISOString(),
      },
    ],
  }) as unknown as WorkspaceRunRow;

describe("runVerdict", () => {
  it("names the failing task, the time, and the attempt's own error", () => {
    const verdict = runVerdict(runOf([attempt("failed")]), graph);
    expect(verdict.status).toBe("failed");
    expect(verdict.headline).toBe("Failed at Train model after 48m");
    expect(verdict.subject).toBe("Train model");
    expect(verdict.elapsed).toBe("48m");
    expect(verdict.tasks).toEqual({ done: 1, total: 3 });
    expect(verdict.attempt).toBeNull();
    expect(verdict.error).toBe("RuntimeError: CUDA out of memory");
  });

  it("says a running attempt is running, and where", () => {
    const running = {
      ...graph,
      task_configs: [{ id: "train", type: "t", label: "Train model", status: "running" }],
    };
    const now = Date.parse("2026-03-01T12:12:00Z");
    expect(runVerdict(runOf([attempt("running")]), running, now).headline).toBe(
      "Running Train model · 12m so far",
    );
  });
});

describe("taskSpans", () => {
  it("draws started tasks on a clock and counts the ones that never started", () => {
    const spans = taskSpans(graph);
    expect(spans.map((span) => [span.key, span.status])).toEqual([
      ["prepare", "succeeded"],
      ["train", "failed"],
    ]);
    expect(spans[1]?.tip).toContain("CUDA out of memory");
    expect(unstartedTasks(graph)).toBe(1);
  });
});

describe("siblingStanding", () => {
  it("ranks the run's duration against the experiment's other finished runs", () => {
    const rows = [sibling("run-a", 30, {}), sibling("run-b", 48, {}), sibling("run-c", 60, {})];
    const standing = siblingStanding("run-b", rows);
    expect(standing.points.find((point) => point.self)?.seconds).toBe(48 * 60);
    expect(standing.rank).toBe("faster than 1 of 2 other runs");
    expect(standing.place).toBe("2/3");
  });

  it("says a tie is a tie", () => {
    const rows = [sibling("run-a", 48, {}), sibling("run-b", 48, {})];
    expect(siblingStanding("run-b", rows).rank).toBe("as long as the 1 other run");
  });
});

describe("distinguishingParameters", () => {
  it("keeps the parameters that set this run apart from its siblings", () => {
    const rows = [
      sibling("run-a", 30, { lr: 0.001, seed: 1 }),
      sibling("run-b", 48, { lr: 0.002, seed: 1 }),
    ];
    expect(distinguishingParameters({ lr: 0.002, seed: 1 }, rows)).toEqual([
      { key: "lr", value: "0.002" },
    ]);
  });
});

describe("resultFigures", () => {
  it("puts numbers first and leaves structured results to their tab", () => {
    expect(resultFigures({ label: "ok", rmse: 0.0123456, nested: { a: 1 } })).toEqual([
      { key: "rmse", value: "0.01235" },
      { key: "label", value: "ok" },
    ]);
  });
});
