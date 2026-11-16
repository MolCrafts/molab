/**
 * Tests for the molq plugin module — its registrations (the run view by
 * scheduler files, the execution columns and detail) and what the run view
 * reads off an attempt's record.
 */

import { beforeEach, describe, expect, it } from "@rstest/core";

import type { ExecutionResponse } from "@/api/generated/models/ExecutionResponse";
import {
  listExecutionColumns,
  listExecutionDetails,
  registerExecutionColumn,
  registerExecutionDetail,
} from "@/app/registry";
import { applicableRunViews } from "@/app/renderers/run/useRunViews";
import { listRunViewContributions } from "@/lib/contribution-runtime";
import { matchesMatcher } from "@/lib/file-type-discovery";
import { createPluginAPI } from "@/plugins/api/create_api";
import { resetContributionRuntimeForTests } from "@/plugins/contribution-runtime";
import {
  executorText,
  isMolqExecutor,
  jobLabel,
  jobSeconds,
  jobVerdict,
  lifetime,
  SCHEDULER_FILES,
  sortSchedulerFiles,
  submissionFacts,
} from "@/plugins/molq/job";
import molqPlugin from "@/plugins/molq/plugin";
import type { ExecutionColumnContribution, ExecutionDetailContribution } from "@/plugins/types";

beforeEach(() => {
  resetContributionRuntimeForTests();
});

const file = (relPath: string, size = 10) => ({
  name: relPath.split("/").pop() ?? relPath,
  relPath,
  type: "file",
  size,
});

const record = (overrides: Partial<ExecutionResponse> = {}): ExecutionResponse => ({
  id: "e01",
  runId: "run-001",
  mode: "initial",
  status: "succeeded",
  createdAt: "2026-03-01T14:02:00Z",
  startedAt: "2026-03-01T14:05:00Z",
  finishedAt: "2026-03-01T14:58:00Z",
  executor: {
    backend: "molq",
    scheduler: "slurm",
    cluster_name: "hpc-slurm",
    scheduler_job_id: "421337",
    target: "hpc-slurm",
  },
  ...overrides,
});

describe("molq run view registration", () => {
  it("registers one run view matched by scheduler files, and no entity tab", async () => {
    const { api } = createPluginAPI("molq");
    await molqPlugin.activate(api);
    const view = listRunViewContributions().find((item) => item.id === "molq");
    expect(view?.label).toBe("Molq");
    expect(view?.order).toBe(30);
    expect(view?.files).toBe(SCHEDULER_FILES);
  });

  it("applies to an attempt with jobs/ scheduler files, not to one without", () => {
    const view = { id: "molq", label: "Molq", files: SCHEDULER_FILES, Component: () => null };
    const molq = applicableRunViews(
      [view],
      [file("jobs/train.sh"), file("jobs/train.out"), file("run.log"), file("out/a.out")],
    );
    expect(molq.map((v) => v.files.map((f) => f.relPath))).toEqual([
      ["jobs/train.sh", "jobs/train.out"],
    ]);
    expect(applicableRunViews([view], [file("run.log"), file("out/train.sh")])).toEqual([]);
  });

  it("matches only flat scheduler files", () => {
    expect(matchesMatcher(SCHEDULER_FILES, file("jobs/train.err"))).toBe(true);
    expect(matchesMatcher(SCHEDULER_FILES, file("jobs/sub/train.err"))).toBe(false);
    expect(matchesMatcher(SCHEDULER_FILES, file("jobs/train.log"))).toBe(false);
  });

  it("orders a job's script, stdout and stderr together", () => {
    const sorted = sortSchedulerFiles([
      file("jobs/train.err"),
      file("jobs/eval.out"),
      file("jobs/train.sh"),
      file("jobs/train.out"),
      file("jobs/eval.sh"),
    ]);
    expect(sorted.map((f) => f.relPath)).toEqual([
      "jobs/eval.sh",
      "jobs/eval.out",
      "jobs/train.sh",
      "jobs/train.out",
      "jobs/train.err",
    ]);
  });
});

describe("the job, from the execution record", () => {
  it("names the job by the scheduler's id and where it ran", () => {
    const executor = executorText(record());
    expect(isMolqExecutor(executor)).toBe(true);
    expect(jobLabel(executor)).toBe("Job 421337");
    expect(jobVerdict(executor)).toBe("Job 421337 on hpc-slurm");
    expect(jobVerdict({ backend: "molq", job_id: "a1b2" })).toBe("Job a1b2");
    expect(jobLabel({})).toBe("Job");
    expect(isMolqExecutor(executorText(record({ executor: { backend: "local" } })))).toBe(false);
  });

  it("lists submission facts in sentence case, known keys first", () => {
    const executor = executorText(
      record({ executor: { ...record().executor, partition: "gpu", job_id: "j-9", empty: null } }),
    );
    expect(submissionFacts(executor)).toEqual([
      ["Backend", "molq"],
      ["Cluster", "hpc-slurm"],
      ["Scheduler", "slurm"],
      ["Job id", "421337"],
      ["Molq job id", "j-9"],
      ["Target", "hpc-slurm"],
      ["Partition", "gpu"],
    ]);
  });

  it("draws the lifetime from submitted, started and ended", () => {
    const value = lifetime(record());
    expect(value.points.map((p) => [p.key, Number(p.fraction.toFixed(3))])).toEqual([
      ["submitted", 0],
      ["started", 0.054],
      ["ended", 1],
    ]);
    expect(value.segments.map((s) => s.kind)).toEqual(["wait", "run"]);
    // submitted and started are too close to print apart: one label.
    expect(value.labels).toHaveLength(2);
    expect(value.labels[0]?.text).toMatch(/^submitted \d\d:\d\d · started \d\d:\d\d$/);
    expect(value.labels[1]?.text).toMatch(/^ended \d\d:\d\d$/);
  });

  it("omits the times the record does not hold", () => {
    const running = lifetime(record({ status: "running", finishedAt: null }));
    expect(running.points.map((p) => p.key)).toEqual(["submitted", "started"]);
    expect(running.segments.map((s) => s.kind)).toEqual(["wait"]);
    const queued = lifetime(record({ status: "queued", startedAt: null, finishedAt: null }));
    expect(queued.points.map((p) => [p.key, p.fraction])).toEqual([["submitted", 0]]);
    expect(queued.segments).toEqual([]);
    expect(lifetime(undefined).points).toEqual([]);
  });

  it("times the job from started to ended only", () => {
    expect(jobSeconds(record())).toBe(53 * 60);
    expect(jobSeconds(record({ finishedAt: null }))).toBeNull();
    expect(jobSeconds(undefined)).toBeNull();
  });
});

describe("execution column registry", () => {
  const Cell = (() => null) as ExecutionColumnContribution["Cell"];

  it("filters by backend so molq columns only appear for molq executions", () => {
    registerExecutionColumn({
      id: "molq:column:cluster",
      backend: "molq",
      columnId: "cluster",
      header: "Cluster",
      Cell,
    });

    expect(listExecutionColumns("molq").map((c) => c.columnId)).toEqual(["cluster"]);
    expect(listExecutionColumns("local")).toEqual([]);
    expect(listExecutionColumns(null)).toEqual([]);
  });

  it("dedupes by id and orders by priority desc", () => {
    registerExecutionColumn({
      id: "a",
      backend: "molq",
      columnId: "scheduler-job",
      header: "Job",
      priority: 10,
      Cell,
    });
    registerExecutionColumn({
      id: "a",
      backend: "molq",
      columnId: "scheduler-job",
      header: "Duplicate (skipped)",
      priority: 999,
      Cell,
    });
    registerExecutionColumn({
      id: "b",
      backend: "molq",
      columnId: "cluster",
      header: "Cluster",
      priority: 100,
      Cell,
    });

    const cols = listExecutionColumns("molq");
    expect(cols.map((c) => c.id)).toEqual(["b", "a"]);
  });
});

describe("execution detail registry", () => {
  it("returns backend-scoped detail contributions", () => {
    const Component = (() => null) as ExecutionDetailContribution["Component"];
    registerExecutionDetail({
      id: "molq:detail:submission",
      backend: "molq",
      title: "Molq submission",
      Component,
    });

    expect(listExecutionDetails("molq")).toHaveLength(1);
    expect(listExecutionDetails("local")).toHaveLength(0);
  });
});
