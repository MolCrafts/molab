import type { AttemptRead, RunAttempt, RunViewHost } from "@molcrafts/molab-plugin";
import { RunViewHostProvider } from "@molcrafts/molab-plugin/ui";
import { describe, expect, it } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";

import type { ExecutionResponse } from "@/api/generated/models/ExecutionResponse";
import { MAX_LINES, MolqFileText, textLines } from "@/plugins/molq/MolqFileText";
import { MolqRunView } from "@/plugins/molq/MolqRunView";
import { molqExecutionKey } from "@/plugins/molq/queries";

const attempt: RunAttempt = {
  projectId: "protein-folding",
  experimentId: "exp-001",
  runId: "run-001",
  executionId: "e01",
  status: "succeeded",
  isLatest: true,
  isRunResult: true,
  dir: "projects/protein-folding/experiments/exp-001/runs/run-001/executions/e01",
};

const files = [
  { name: "train.err", relPath: "jobs/train.err", type: "file", size: 0 },
  { name: "train.sh", relPath: "jobs/train.sh", type: "file", size: 1024 },
];

const idle: AttemptRead<string> = {
  data: undefined,
  loading: false,
  error: null,
  refetch: () => {},
};

const host: RunViewHost = {
  attempt,
  useAttemptText: () => idle,
  useAttemptBlob: () => idle,
  openFile: () => {},
  openLogs: () => {},
};

const render = (record: Partial<ExecutionResponse> | null): string => {
  const client = new QueryClient();
  if (record) {
    client.setQueryData(molqExecutionKey(attempt), {
      id: "e01",
      runId: "run-001",
      mode: "initial",
      status: "succeeded",
      createdAt: "2026-03-01T14:02:00Z",
      startedAt: "2026-03-01T14:05:00Z",
      finishedAt: "2026-03-01T14:58:00Z",
      ...record,
    });
  }
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <RunViewHostProvider value={host}>
        <MolqRunView attempt={attempt} files={files} />
      </RunViewHostProvider>
    </QueryClientProvider>,
  );
};

describe("MolqRunView", () => {
  it("shows the job first: verdict, duration, lifetime and submission facts", () => {
    const html = render({
      executor: {
        backend: "molq",
        cluster_name: "hpc-slurm",
        scheduler: "slurm",
        scheduler_job_id: "421337",
        target: "hpc-slurm",
      },
    });
    expect(html).toContain("Job 421337 on hpc-slurm");
    expect(html).toContain("53m");
    expect(html).toContain("Lifetime");
    expect(html).toContain("Submission");
    expect(html).toContain("Cluster");
    expect(html).toContain("Job id");
    // The files: the job, then the script before its stderr, with sizes.
    expect(html.indexOf("Job 421337<")).toBeLessThan(html.indexOf("jobs/train.sh"));
    expect(html.indexOf("jobs/train.sh")).toBeLessThan(html.indexOf("jobs/train.err"));
    expect(html).toContain("1.0 KB");
    // No old chrome: tabs, banners or the Field / Value table.
    expect(html).not.toContain("Selected execution");
    expect(html).not.toContain("Field");
  });

  it("says when the attempt did not run through Molq", () => {
    const html = render({ executor: { backend: "local" } });
    expect(html).toContain("Not a Molq attempt");
    expect(html).not.toContain("Lifetime");
  });

  it("is loading until the record arrives", () => {
    expect(render(null)).toContain('aria-busy="true"');
  });
});

describe("MolqFileText", () => {
  it("numbers lines and marks error lines", () => {
    const html = renderToStaticMarkup(
      <MolqFileText text={"step 1\nslurmstepd: error: task exited\n"} />,
    );
    expect(html).toContain('data-line="1"');
    expect(html).toContain('data-line="2"');
    expect(html).not.toContain('data-line="3"');
    expect(html).toMatch(/text-status-failed-foreground[^>]*>slurmstepd: error/);
  });

  it("shows the tail of a long file with its true line numbers", () => {
    const text = Array.from({ length: MAX_LINES + 10 }, (_, i) => `line ${i + 1}`).join("\n");
    const html = renderToStaticMarkup(<MolqFileText text={text} />);
    expect(html).toContain("Lines 1–10 are not shown");
    expect(html).toContain(`data-line="${MAX_LINES + 10}"`);
    expect(html).not.toContain('data-line="10"');
  });

  it("drops only the empty line after a final newline", () => {
    expect(textLines("a\nb\n")).toEqual(["a", "b"]);
    expect(textLines("a\n\n")).toEqual(["a", ""]);
  });
});
