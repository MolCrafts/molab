import { describe, expect, it } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import { attemptTasksText, RunAttemptsPanel } from "@/app/renderers/RunAttemptsPanel";
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
  executor: {},
  environment: {},
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
  it("says a run with no attempts has not started", () => {
    const html = story(<RunOverview run={run([])} attempt={null} outputs={null} />);
    expect(html).toContain("Not started");
    expect(html).not.toContain("sha256:def");
  });

  it("leads with one verdict line and its evidence, never a tally", () => {
    const history = [
      execution("e01", "failed", "initial"),
      execution("e02", "succeeded", "resume"),
    ];
    const html = story(
      <RunOverview
        run={run(history)}
        attempt={history[1] ?? null}
        outputs={{
          executionId: "e02",
          results: { rmse: 0.01234567, epochs: 40, notes: { nested: true } },
        }}
      />,
    );
    // Retrofit R3: the glyph carries the status (its name), the line says what.
    expect(html).toContain('aria-label="Succeeded"');
    expect(html).toContain(">5m<");
    // Scalar results are the evidence; structured values stay on their tab.
    expect(html).toContain("rmse 0.012346");
    expect(html).toContain("epochs 40");
    expect(html).not.toContain("nested");
    expect(html).not.toContain("tasks done");
    expect(html).not.toContain("Knowledge");
  });

  it("reads the attempt the page shows, not always the latest", () => {
    const history = [
      execution("e01", "failed", "initial", { type: "WorkflowError", message: "scheduler died" }),
      execution("e02", "succeeded", "resume"),
    ];
    const html = story(
      <RunOverview run={run(history)} attempt={history[0] ?? null} outputs={null} />,
    );
    expect(html).toContain('aria-label="Failed"');
    expect(html).toContain("scheduler died");
    expect(html).not.toContain('aria-label="Succeeded"');
  });

  it("puts a failure's message on the evidence line, the full error behind it", () => {
    const failed = execution("e01", "failed", "initial", {
      type: "WorkflowError",
      message: "scheduler died",
    });
    const html = story(<RunOverview run={run([failed], "boom")} attempt={failed} outputs={null} />);
    expect(html).toContain('aria-label="Failed"');
    expect(html).toContain("scheduler died");
    expect(html).toContain('aria-expanded="false"');
    // Collapsed: the type-prefixed error and the jump to Logs wait for a click.
    expect(html).not.toContain("WorkflowError: scheduler died");
  });

  it("lists what a success registered, each with where it opens", () => {
    const done = execution("e01", "succeeded");
    const html = story(
      <RunOverview
        run={run([done])}
        attempt={done}
        outputs={{
          executionId: "e01",
          assets: [
            {
              id: "asset-1",
              title: "trajectory",
              createdAt: "2026-03-01T12:00:00Z",
              ref: "molab:asset/asset-1",
              digest: "abc",
              size: 2_400_000,
              file: "trajectory.xyz",
              mediaType: "chemical/x-xyz",
              originKind: "execution",
            },
          ],
          evidence: [{ kind: "log", path: "run.log", size: 1000 }],
        }}
        openIn={(file) =>
          file.name.endsWith(".xyz") ? { value: "molvis", label: "MolVis" } : null
        }
        onOpenView={() => undefined}
      />,
    );
    expect(html).toContain("Outputs");
    expect(html).toContain("trajectory.xyz");
    expect(html).toContain("chemical/x-xyz");
    expect(html).toContain("MolVis");
    expect(html).toContain("Logs");
  });
});

describe("RunAttemptsPanel", () => {
  const panel = (history: ExecutionRecordSummary[], selected: string, outputs = null as never) =>
    renderToStaticMarkup(
      <QueryClientProvider client={new QueryClient()}>
        <RunAttemptsPanel
          run={run(history)}
          selectedExecutionId={selected}
          onSelectExecution={() => undefined}
          onPreviewExecution={() => undefined}
          onInspectTask={() => undefined}
          outputs={outputs}
          logsError={null}
        />
      </QueryClientProvider>,
    );

  it("lists attempts newest first and marks the page's one", () => {
    const html = panel(
      [
        execution("e01", "failed"),
        { ...execution("e02", "succeeded", "resume"), basedOnExecutionId: "e01" },
      ],
      "e01",
    );
    expect(html.indexOf(">e02<")).toBeLessThan(html.indexOf(">e01<"));
    expect(html).toContain('aria-selected="true"');
    expect(html).toContain(">resume<");
    const files = html.search(/Files of e01/);
    const workflow = html.search(/Workflow\s*</);
    expect(files).toBeGreaterThan(-1);
    expect(workflow).toBeGreaterThan(files);
  });

  it("leads a failed attempt with its error and opens stderr", () => {
    const html = panel(
      [execution("e01", "failed", "initial", { type: "WorkflowError", message: "scheduler died" })],
      "e01",
      { executionId: "e01", stderr: "traceback line" } as never,
    );
    const alert = html.indexOf("WorkflowError: scheduler died");
    expect(alert).toBeGreaterThan(-1);
    expect(alert).toBeLessThan(html.search(/Files of e01/));
    expect(html).toContain("Read stderr in Files.");
    expect(html).toContain("traceback line");
  });

  it("says what each attempt did with its tasks", () => {
    expect(attemptTasksText(null)).toBe("—");
    expect(
      attemptTasksText({
        task_configs: [
          { id: "a", type: "t", status: "cached" },
          { id: "b", type: "t", status: "completed" },
          { id: "c", type: "t", status: "completed" },
        ],
        links: [],
      }),
    ).toBe("1 reused · 2 run");
    expect(
      attemptTasksText({
        task_configs: [
          { id: "a", type: "t", status: "completed" },
          { id: "b", type: "t", status: "failed" },
          { id: "c", type: "t" },
        ],
        links: [],
      }),
    ).toBe("1 of 3");
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
