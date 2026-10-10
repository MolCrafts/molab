import { performance } from "node:perf_hooks";
import { applyFilters, computeFacetCounts } from "../src/app/runs/aggregates";
import { paginate, sortJobs } from "../src/app/runs/jobsTable";
import type { WorkspaceRunRow } from "../src/app/runs/types";

const NOW = Date.parse("2026-08-31T00:00:00Z");
const STATUSES = ["running", "pending", "succeeded", "failed"] as const;
const BACKENDS = ["local", "slurm", "molq"] as const;

const makeRuns = (count: number): WorkspaceRunRow[] =>
  Array.from({ length: count }, (_, index) => {
    const createdAt = new Date(NOW - index * 60_000).toISOString();
    const status = STATUSES[index % STATUSES.length];
    const backend = BACKENDS[index % BACKENDS.length];
    return {
      id: `run-${index.toString().padStart(5, "0")}`,
      name: `Run ${index}`,
      projectId: `project-${index % 8}`,
      projectName: `Project ${index % 8}`,
      experimentId: `experiment-${index % 32}`,
      experimentName: `Experiment ${index % 32}`,
      status,
      backend,
      cluster: backend === "local" ? null : `cluster-${index % 4}`,
      scheduler: backend === "local" ? null : "slurm",
      target: `target-${index % 6}`,
      profile: "default",
      parameters: { seed: index, learningRate: 0.001 },
      createdAt,
      finishedAt: status === "succeeded" || status === "failed" ? createdAt : null,
      executionCount: 1,
      latestSchedulerJobId: backend === "local" ? null : `job-${index}`,
      executions: [
        {
          executionId: `execution-${index}`,
          runId: `run-${index.toString().padStart(5, "0")}`,
          status,
          startedAt: createdAt,
          finishedAt: status === "succeeded" || status === "failed" ? createdAt : null,
          durationSeconds: index % 3600,
          schedulerJobId: backend === "local" ? null : `job-${index}`,
          backend,
          metadata: {},
          backendMetadata: {},
        },
      ],
    };
  });

const percentile = (values: number[], fraction: number): number => {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * fraction))] ?? 0;
};

const measure = (count: number): object => {
  const rows = makeRuns(count);
  const iterations = count <= 100 ? 200 : count <= 1000 ? 80 : 40;
  const samples: number[] = [];
  let visible = 0;

  const pipeline = (): void => {
    const filtered = applyFilters(
      rows,
      { status: ["running", "failed"], backend: ["slurm", "molq"] },
      NOW,
    );
    computeFacetCounts(rows, { backend: ["slurm"] }, NOW);
    visible = paginate(sortJobs(filtered, { key: "submitted", dir: "desc" }), 1, 50).items.length;
  };

  for (let index = 0; index < 10; index += 1) pipeline();
  for (let index = 0; index < iterations; index += 1) {
    const start = performance.now();
    pipeline();
    samples.push(performance.now() - start);
  }

  return {
    rows: count,
    iterations,
    visible,
    medianMs: Number(percentile(samples, 0.5).toFixed(3)),
    p95Ms: Number(percentile(samples, 0.95).toFixed(3)),
  };
};

console.log(JSON.stringify([100, 1000, 2000].map(measure), null, 2));
