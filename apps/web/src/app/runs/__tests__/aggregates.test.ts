import { describe, expect, it } from "@rstest/core";
import { applyFilters, computeFacetCounts, computeRecentEventsForRun } from "@/app/runs/aggregates";
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
  checkpointArtifactId: null,
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
    inputAssetIds: [],
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

  it("supports the active quick view", () => {
    const runs = [
      run({ id: "a", status: "running" }),
      run({ id: "b", status: "pending" }),
      run({ id: "c", status: "succeeded" }),
    ];
    expect(
      applyFilters(runs, { quickView: ["active"] }, NOW)
        .map((item) => item.id)
        .sort(),
    ).toEqual(["a", "b"]);
  });

  it("excludes failed runs older than 24 hours", () => {
    const fresh = run({
      id: "fresh",
      status: "failed",
      finishedAt: new Date(NOW - 2 * HOUR).toISOString(),
    });
    const stale = run({
      id: "stale",
      status: "failed",
      finishedAt: new Date(NOW - 30 * HOUR).toISOString(),
    });
    expect(applyFilters([fresh, stale], { quickView: ["failed24h"] }, NOW)).toEqual([fresh]);
  });

  it("detects long-running executions", () => {
    // A Run has no scalar status: "still running" is a property of an
    // attempt, so the attempt is what has to say so.
    const long = run({
      id: "long",
      executions: [
        exec({
          status: "running",
          startedAt: new Date(NOW - 90 * MIN).toISOString(),
          finishedAt: null,
        }),
      ],
    });
    const short = run({
      id: "short",
      executions: [
        exec({
          status: "running",
          startedAt: new Date(NOW - 10 * MIN).toISOString(),
          finishedAt: null,
        }),
      ],
    });
    expect(applyFilters([long, short], { quickView: ["longRunning"] }, NOW)).toEqual([long]);
  });
});

describe("computeRecentEventsForRun", () => {
  it("emits real submitted, started, and finished events in descending order", () => {
    const events = computeRecentEventsForRun(
      run({
        id: "r1",
        createdAt: new Date(NOW - HOUR).toISOString(),
        executions: [
          exec({
            executionId: "e1",
            startedAt: new Date(NOW - 50 * MIN).toISOString(),
            finishedAt: new Date(NOW - 5 * MIN).toISOString(),
            status: "succeeded",
          }),
        ],
      }),
    );
    expect(events.map((event) => event.kind)).toEqual(["finished", "started", "submitted"]);
    expect(events[0].outcome).toBe("succeeded");
    expect(events[1].executionId).toBe("e1");
  });

  it("never invents unsupported event kinds", () => {
    const kinds = new Set(
      computeRecentEventsForRun(
        run({ executions: [exec({}), exec({ executionId: "e2", finishedAt: null })] }),
      ).map((event) => event.kind),
    );
    for (const kind of kinds) {
      expect(["submitted", "started", "finished"]).toContain(kind);
    }
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
    expect(Object.fromEntries(facets.backend.map((item) => [item.value, item.count]))).toEqual({
      slurm: 2,
      local: 2,
    });
  });
});
