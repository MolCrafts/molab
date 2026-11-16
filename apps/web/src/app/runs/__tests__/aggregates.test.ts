import { describe, expect, it } from "@rstest/core";
import { applyFilters, computeFacetCounts } from "@/app/runs/aggregates";
import type {
  WorkspaceExecutionRow,
  WorkspaceRunRow,
  WorkspaceRunsFilters,
} from "@/app/runs/types";

const NOW = Date.parse("2026-04-27T12:00:00Z");
const MIN = 60_000;
const HOUR = 60 * MIN;

const exec = (over: Partial<WorkspaceExecutionRow>): WorkspaceExecutionRow => ({
  executionId: "exec-1",
  runId: "run-1",
  mode: "initial",
  status: "succeeded",
  createdAt: new Date(NOW - 35 * MIN).toISOString(),
  startedAt: new Date(NOW - 30 * MIN).toISOString(),
  finishedAt: new Date(NOW - 5 * MIN).toISOString(),
  durationSeconds: 1500,
  schedulerJobId: null,
  backend: "local",
  basedOnExecutionId: null,
  backendMetadata: {},
  ...over,
});

type RunFixtureOverrides = Partial<Omit<WorkspaceRunRow, "executions" | "statusSummary">> & {
  status?: string;
  backend?: string;
  cluster?: string | null;
  target?: string | null;
  profile?: string | null;
  finishedAt?: string | null;
  executions?: WorkspaceExecutionRow[];
};

const run = (over: RunFixtureOverrides): WorkspaceRunRow => {
  const status = over.status === "pending" ? "queued" : (over.status ?? "succeeded");
  const finishedAt =
    over.finishedAt === undefined
      ? status === "running" || status === "queued"
        ? null
        : new Date(NOW - 5 * MIN).toISOString()
      : over.finishedAt;
  const executions = over.executions ?? [
    exec({
      status,
      finishedAt,
      backend: over.backend ?? "local",
      backendMetadata: {
        ...(over.cluster ? { cluster_name: over.cluster } : {}),
        ...(over.target ? { target: over.target } : {}),
        ...(over.profile ? { profile: over.profile } : {}),
      },
    }),
  ];
  const byStatus = Object.fromEntries(
    [...new Set(executions.map((execution) => execution.status))].map((value) => [
      value,
      executions.filter((execution) => execution.status === value).length,
    ]),
  );
  const {
    status: _status,
    backend: _backend,
    cluster: _cluster,
    target,
    profile: _profile,
    finishedAt: _finishedAt,
    ...rowOverrides
  } = over;
  return {
    id: "run-1",
    name: "Run 1",
    workspaceKey: "ws",
    path: "projects/proj-A/experiments/exp-1/runs/Run 1",
    projectId: "proj-A",
    projectName: "Project A",
    experimentId: "exp-1",
    experimentName: "Experiment 1",
    definitionHash: "sha256:definition",
    experimentRevisionId: "revision-1",
    inputs: [],
    targetHint: target ?? null,
    statusSummary: {
      total: executions.length,
      active: executions.filter((execution) =>
        ["queued", "running", "finalizing"].includes(execution.status),
      ).length,
      notStarted: executions.length === 0,
      byStatus,
    },
    parameters: {},
    createdAt: new Date(NOW - HOUR).toISOString(),
    executions,
    ...rowOverrides,
  };
};

describe("applyFilters", () => {
  it("returns all runs when filters are empty", () => {
    expect(
      applyFilters([run({ id: "a" }), run({ id: "b", status: "running" })], {}, NOW),
    ).toHaveLength(2);
  });

  it("ANDs across array filters and ORs within a single filter", () => {
    const runs = [
      run({ id: "a", status: "running", backend: "slurm" }),
      run({ id: "b", status: "running", backend: "local" }),
      run({ id: "c", status: "failed", backend: "slurm" }),
    ];
    const filters: WorkspaceRunsFilters = {
      status: ["running", "failed"],
      backend: ["slurm"],
    };
    expect(applyFilters(runs, filters, NOW).map((item) => item.id)).toEqual(["a", "c"]);
  });

  it("filters a run by its latest attempt, not by any attempt in its history", () => {
    const NOW_ISO = new Date(NOW).toISOString();
    const runs = [
      run({
        id: "recovered",
        executions: [
          exec({
            executionId: "e01",
            status: "failed",
            createdAt: new Date(NOW - 2 * HOUR).toISOString(),
          }),
          exec({ executionId: "e02", status: "succeeded", createdAt: NOW_ISO }),
        ],
      }),
      run({ id: "broken", status: "failed" }),
      run({ id: "closing", status: "finalizing" }),
    ];
    expect(applyFilters(runs, { status: ["failed"] }, NOW).map((item) => item.id)).toEqual([
      "broken",
    ]);
    expect(applyFilters(runs, { status: ["running"] }, NOW).map((item) => item.id)).toEqual([
      "closing",
    ]);
  });

  it("keeps runs started within the Started window", () => {
    const fresh = run({
      id: "fresh",
      createdAt: new Date(NOW - 2 * HOUR).toISOString(),
      executions: [],
    });
    const old = run({
      id: "old",
      createdAt: new Date(NOW - 30 * HOUR).toISOString(),
      executions: [],
    });
    expect(applyFilters([fresh, old], { started: ["24h"] }, NOW)).toEqual([fresh]);
    expect(applyFilters([fresh, old], { started: ["7d"] }, NOW)).toHaveLength(2);
  });

  it("reads the bar's free tokens like an experiment's Runs filter", () => {
    const runs = [
      run({ id: "a", parameters: { driver: "ase", timestep_fs: 2 } }),
      run({ id: "b", parameters: { driver: "lib_md3", timestep_fs: 1 } }),
      run({ id: "c", experimentName: "Thermostat Validation" }),
    ];
    expect(applyFilters(runs, { q: "driver:ase" }, NOW).map((item) => item.id)).toEqual(["a"]);
    expect(applyFilters(runs, { q: "timestep_fs>1" }, NOW).map((item) => item.id)).toEqual(["a"]);
    expect(applyFilters(runs, { q: "thermostat" }, NOW).map((item) => item.id)).toEqual(["c"]);
  });
});

describe("computeFacetCounts", () => {
  it("counts each facet while ignoring its own filter", () => {
    const runs = [
      run({ id: "1", status: "running", backend: "slurm" }),
      run({ id: "2", status: "failed", backend: "slurm" }),
      run({ id: "3", status: "running", backend: "local" }),
      run({ id: "4", status: "succeeded", backend: "local" }),
    ];
    const facets = computeFacetCounts(runs, { backend: ["slurm"] }, NOW);
    expect(Object.fromEntries(facets.status.map((item) => [item.value, item.count]))).toEqual({
      running: 1,
      failed: 1,
    });
    expect(facets.status.map((item) => item.label)).toEqual(["Running", "Failed"]);
    expect(Object.fromEntries(facets.backend.map((item) => [item.value, item.count]))).toEqual({
      slurm: 2,
      local: 2,
    });
  });
});

describe("status facet", () => {
  it("counts each run once, by its latest attempt — what picking the facet shows", () => {
    const recovered = run({
      id: "recovered",
      executions: [
        exec({
          executionId: "e1",
          status: "failed",
          startedAt: new Date(NOW - 50 * MIN).toISOString(),
        }),
        exec({
          executionId: "e2",
          status: "succeeded",
          startedAt: new Date(NOW - 20 * MIN).toISOString(),
        }),
      ],
    });
    const broken = run({ id: "broken", status: "failed" });
    const facets = computeFacetCounts([recovered, broken], {}, NOW);
    const counts = Object.fromEntries(facets.status.map((item) => [item.value, item.count]));
    expect(counts).toEqual({ succeeded: 1, failed: 1 });
    expect(applyFilters([recovered, broken], { status: ["failed"] }, NOW)).toHaveLength(
      counts.failed,
    );
  });
});
