import { describe, expect, it } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import { RunExecutionsPanel } from "@/app/renderers/RunExecutionsPanel";
import {
  failedTask,
  failureHeadline,
  preferredFailureOutput,
} from "@/app/renderers/run/executionFailure";
import { RunOverview } from "@/app/renderers/run/RunOverview";
import type { ExecutionRecordSummary, RunSummary } from "@/app/types";

const execution = (
  executionId: string,
  status: string,
  mode = "initial",
  error: ExecutionRecordSummary["error"] = null,
): ExecutionRecordSummary => ({
  executionId,
  mode,
  createdAt: "2026-03-01T12:00:00Z",
  startedAt: "2026-03-01T12:00:00Z",
  finishedAt: "2026-03-01T12:05:00Z",
  status,
  basedOnExecutionId: null,
  checkpointArtifactId: null,
  executor: {},
  environment: {},
  artifactIds: [],
  error,
});

const run = (
  history: ExecutionRecordSummary[],
  errorMessage: string | null = null,
): RunSummary => ({
  id: "run-abc",
  name: "lr=0.001",
  path: "projects/proj-alpha/experiments/exp-001/runs/lr=0.001",
  status: (history.at(-1)?.status ?? "pending") as RunSummary["status"],
  summary: "",
  updatedAt: "2026-03-01T12:00:00Z",
  projectId: "proj-alpha",
  experimentId: "exp-001",
  definitionHash: "sha256:def",
  experimentRevisionId: "rev-1",
  statusSummary: {
    total: history.length,
    active: 0,
    notStarted: history.length === 0,
    byStatus: {},
  },
  parameters: { lr: 0.001 },
  workflowSource: null,
  workflowSnapshot: null,
  startedAt: history[0]?.startedAt ?? null,
  finishedAt: history.at(-1)?.finishedAt ?? null,
  executionHistory: history,
  errorMessage,
});

const story = (node: ReactNode): string =>
  renderToStaticMarkup(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );

describe("RunOverview", () => {
  it("says a run with no attempts has not been run", () => {
    const html = story(<RunOverview run={run([])} />);
    expect(html).toContain("Not run yet");
    expect(html).toContain("0 attempts");
    expect(html).not.toContain("sha256:def");
    expect(html).not.toContain("Definition");
  });

  it("leads with a verdict sentence, not a gauge of one item", () => {
    const html = story(
      <RunOverview
        run={run([execution("e01", "failed", "initial"), execution("e02", "succeeded", "resume")])}
        results={{ rmse: 0.01234567, epochs: 40, notes: { nested: true } }}
      />,
    );
    expect(html).toContain("Completed in 5m");
    expect(html).toContain("attempt 2 of 2, a resume");
    expect(html).not.toContain("success");
    expect(html).not.toContain(">e01");
    // Scalar results are the run's science; structured values stay on their tab.
    expect(html).toContain("0.01235");
    expect(html).toContain("40");
    expect(html).not.toContain("nested");
    expect(html).not.toContain("sha256:def");
  });

  it("puts a failed attempt's own error under the verdict", () => {
    const html = story(
      <RunOverview
        run={run(
          [
            execution("e01", "failed", "initial", {
              type: "WorkflowError",
              message: "scheduler died",
            }),
          ],
          "boom",
        )}
      />,
    );
    expect(html).toContain("Failed after 5m");
    expect(html).toContain("WorkflowError: scheduler died");
    expect(html).not.toContain(">Attempts<");
  });
});

describe("RunExecutionsPanel", () => {
  it("keeps the attempt list apart from one execution, workflow before outputs", () => {
    const html = renderToStaticMarkup(
      <QueryClientProvider client={new QueryClient()}>
        <RunExecutionsPanel
          run={run([execution("e01", "failed"), execution("e02", "succeeded", "resume")])}
          selectedExecutionId="e02"
          onSelectExecution={() => undefined}
          onInspectTask={() => undefined}
          outputs={null}
          logsError={null}
        />
      </QueryClientProvider>,
    );
    const workflow = html.search(/Workflow\s*</);
    const outputs = html.search(/Outputs\s*</);
    expect(html).toContain("Executions");
    expect(html).toContain("e01");
    expect(html).toContain("e02");
    expect(workflow).toBeGreaterThan(-1);
    expect(outputs).toBeGreaterThan(workflow);
  });

  it("leads a failed attempt with its error and opens stderr", () => {
    const html = renderToStaticMarkup(
      <QueryClientProvider client={new QueryClient()}>
        <RunExecutionsPanel
          run={run([
            execution("e01", "failed", "initial", {
              type: "WorkflowError",
              message: "scheduler died",
            }),
          ])}
          selectedExecutionId="e01"
          onSelectExecution={() => undefined}
          onInspectTask={() => undefined}
          outputs={{ executionId: "e01", stderr: "traceback line" }}
          logsError={null}
        />
      </QueryClientProvider>,
    );
    const alert = html.indexOf("WorkflowError: scheduler died");
    const workflow = html.search(/Workflow\s*</);
    const outputs = html.search(/Outputs\s*</);
    expect(alert).toBeGreaterThan(-1);
    expect(alert).toBeLessThan(workflow);
    expect(html).toContain("Read stderr in Outputs.");
    expect(html).toContain("traceback line");
    expect(workflow).toBeLessThan(outputs);
  });
});

describe("execution failure evidence", () => {
  it("names the failed task and prefers its out directory over stderr", () => {
    const graph = {
      task_configs: [
        { id: "prepare", type: "fn", status: "completed" },
        { id: "simulate", type: "fn", status: "failed", error: "RuntimeError: boom" },
      ],
      links: [],
    };
    const task = failedTask(graph);
    expect(task).toEqual({ id: "simulate", error: "RuntimeError: boom" });
    expect(
      failureHeadline({
        status: "failed",
        error: { type: "WorkflowError", message: "workflow failed" },
        task,
      }),
    ).toBe("simulate failed. RuntimeError: boom");
    expect(
      preferredFailureOutput("simulate", {
        executionId: "e01",
        stderr: "traceback line",
        unregistered: [
          { name: "log.lammps", relPath: "out/simulate/log.lammps", type: "file" },
          { name: "other.log", relPath: "out/prepare/other.log", type: "file" },
        ],
      }),
    ).toEqual({ kind: "file", path: "out/simulate/log.lammps" });
    expect(
      preferredFailureOutput("simulate", { executionId: "e01", stderr: "traceback line" }),
    ).toEqual({ kind: "stdio", name: "stderr" });
    expect(failureHeadline({ status: "succeeded", error: null, task })).toBeNull();
    expect(preferredFailureOutput("simulate", { executionId: "e01", stderr: null })).toBeNull();
  });
});
