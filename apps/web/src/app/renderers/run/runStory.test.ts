import { describe, expect, it } from "@rstest/core";

import {
  clockWindow,
  errorLine,
  resultFigures,
  runResultExecution,
  runVerdict,
  taskClock,
} from "@/app/renderers/run/runStory";
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

describe("runVerdict", () => {
  it("names the failing task and keeps the error's message as the evidence", () => {
    const verdict = runVerdict(runOf([attempt("failed")]), graph);
    expect(verdict.status).toBe("failed");
    expect(verdict.word).toBe("Failed");
    expect(verdict.subject).toBe("at Train model");
    expect(verdict.elapsed).toBe("48m");
    expect(verdict.evidence).toBe("CUDA out of memory");
    expect(verdict.error).toBe("RuntimeError: CUDA out of memory");
    expect(verdict.taskId).toBe("train");
  });

  it("says an interrupted attempt was interrupted, and how far it got", () => {
    const verdict = runVerdict(runOf([attempt("interrupted")]), graph);
    expect(verdict.word).toBe("Interrupted");
    expect(verdict.subject).toBe("at Train model");
    expect(verdict.evidence).toBe(
      "Train model failed · 1 of 3 tasks finished".replace(
        "Train model failed",
        "RuntimeError: CUDA out of memory",
      ),
    );
  });

  it("reads the latest attempt, not an earlier success", () => {
    const verdict = runVerdict(runOf([attempt("succeeded"), attempt("failed")]), graph);
    expect(verdict.status).toBe("failed");
  });

  it("puts a success's time in its subject and its results in the evidence", () => {
    const verdict = runVerdict(runOf([attempt("succeeded")]), graph, Date.now(), [
      { key: "energy_drift", value: "1.50e-4" },
      { key: "frames", value: "51" },
    ]);
    expect(verdict.subject).toBe("in 48m");
    expect(verdict.elapsed).toBeNull();
    expect(verdict.evidence).toBe("energy_drift 1.50e-4 · frames 51");
  });

  it("says a running attempt is running, which task, and for how long", () => {
    const running = {
      ...graph,
      task_configs: [{ id: "train", type: "t", label: "Train model", status: "running" }],
    };
    const now = Date.parse("2026-03-01T12:12:00Z");
    const verdict = runVerdict(runOf([attempt("running")]), running, now);
    expect(verdict.subject).toBe("Train model");
    expect(verdict.elapsed).toBe("12m so far");
  });

  it("says where a queued resume waits and what it reuses", () => {
    const queued = {
      ...attempt("queued", "resume"),
      executionId: "e02",
      basedOnExecutionId: "e01",
      finishedAt: null,
      executor: { target: "hpc-slurm" },
    };
    const journal = {
      ...graph,
      task_configs: [
        { id: "prepare", type: "p", label: "Prepare", status: "cached" },
        { id: "train", type: "t", label: "Train model" },
        { id: "evaluate", type: "e", label: "Evaluate" },
      ],
    };
    const verdict = runVerdict(runOf([attempt("failed"), queued]), journal);
    expect(verdict.subject).toBe("on hpc-slurm");
    expect(verdict.evidence).toBe("Resume of e01 · 1 reused · 2 tasks to run");
    expect(taskClock(journal, queued).map((row) => row.note)).toEqual([
      "reused from e01",
      "waiting",
      "waiting",
    ]);
  });
});

describe("taskClock", () => {
  it("draws every task in order: a bar for the ones that ran, a word for the rest", () => {
    const rows = taskClock(graph, attempt("failed"));
    expect(rows.map((row) => [row.key, row.status, row.note])).toEqual([
      ["prepare", "succeeded", null],
      ["train", "failed", null],
      ["evaluate", rows[2]?.status, "not run"],
    ]);
    expect(rows[1]?.tip).toContain("CUDA out of memory");
    expect(clockWindow(rows)).toMatch(/^\d\d:\d\d → \d\d:\d\d$/);
  });
});

describe("errorLine", () => {
  it("finds the line that carries the error, else the last traceback", () => {
    const text = "step 1\nTraceback (most recent call last):\nRuntimeError: CUDA out of memory\n";
    expect(errorLine(text, "RuntimeError: CUDA out of memory")).toBe(3);
    expect(errorLine(text, "something else entirely")).toBe(2);
    expect(errorLine(null, "x")).toBeNull();
  });
});

describe("run result", () => {
  it("keeps the latest sealed success when a later attempt is still running", () => {
    const history = [
      { ...attempt("succeeded"), executionId: "e01" },
      { ...attempt("running"), executionId: "e02", finishedAt: null },
    ];
    expect(runResultExecution(history)?.execution.executionId).toBe("e01");
    expect(runResultExecution(history)?.index).toBe(1);
    expect(runResultExecution([attempt("failed")])).toBeNull();
  });
});

describe("resultFigures", () => {
  it("puts numbers first and leaves structured results to their tab", () => {
    expect(resultFigures({ label: "ok", rmse: 0.0123456, nested: { a: 1 } })).toEqual([
      { key: "rmse", value: "0.012346" },
      { key: "label", value: "ok" },
    ]);
    expect(resultFigures({ energy_drift: 0.00015 })[0]?.value).toBe("1.50e-4");
  });
});
