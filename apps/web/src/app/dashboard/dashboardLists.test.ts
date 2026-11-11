import { describe, expect, it } from "@rstest/core";

import { dashboardLists } from "@/app/dashboard/dashboardLists";
import type { WorkspaceRunRow } from "@/app/runs/types";

interface Attempt {
  status: string;
  startedAt: string | null;
  finishedAt: string | null;
}

const run = (
  id: string,
  attempts: Attempt[],
  scope: { projectId?: string; experimentId?: string } = {},
): WorkspaceRunRow => {
  const latest = attempts[attempts.length - 1]?.status ?? "pending";
  return {
    id,
    name: id,
    workspaceKey: "ws",
    path: `projects/p/experiments/e/runs/${id}`,
    projectId: scope.projectId ?? "p1",
    projectName: scope.projectId ?? "p1",
    experimentId: scope.experimentId ?? "e1",
    experimentName: scope.experimentId ?? "e1",
    definitionHash: `definition-${id}`,
    experimentRevisionId: "revision-1",
    inputs: [],
    targetHint: null,
    statusSummary: {
      total: attempts.length,
      active: latest === "running" || latest === "queued" ? 1 : 0,
      notStarted: attempts.length === 0,
      byStatus: { [latest]: 1 },
    },
    parameters: {},
    createdAt: attempts[0]?.startedAt ?? "2026-11-01T00:00:00Z",
    executions: attempts.map((attempt, index) => ({
      executionId: `e${index + 1}`,
      runId: id,
      mode: index === 0 ? "initial" : "resume",
      status: attempt.status,
      createdAt: attempt.startedAt ?? "2026-11-01T00:00:00Z",
      startedAt: attempt.startedAt,
      finishedAt: attempt.finishedAt,
      durationSeconds: 0,
      basedOnExecutionId: null,
      schedulerJobId: null,
      backend: null,
      backendMetadata: {},
    })),
  } as WorkspaceRunRow;
};

const done = (status: string, start: string, end: string): Attempt => ({
  status,
  startedAt: start,
  finishedAt: end,
});

const NOW = Date.parse("2026-11-08T20:00:00Z");

describe("dashboardLists", () => {
  const rows = [
    run("ok-old", [done("succeeded", "2026-11-06T10:00:00Z", "2026-11-06T11:00:00Z")]),
    run("ok-new", [done("succeeded", "2026-11-08T10:00:00Z", "2026-11-08T11:00:00Z")]),
    run("resumed", [
      done("failed", "2026-11-08T08:00:00Z", "2026-11-08T09:00:00Z"),
      done("succeeded", "2026-11-08T12:00:00Z", "2026-11-08T13:00:00Z"),
    ]),
    run("broke", [done("failed", "2026-11-08T14:00:00Z", "2026-11-08T15:00:00Z")]),
    run("stopped", [done("interrupted", "2026-11-08T16:00:00Z", "2026-11-08T17:00:00Z")]),
    run("waiting", [{ status: "queued", startedAt: null, finishedAt: null }]),
    run("going", [{ status: "running", startedAt: "2026-11-08T19:00:00Z", finishedAt: null }]),
  ];

  it("puts each run in one list by its latest attempt", () => {
    const lists = dashboardLists(rows, NOW);
    expect(lists.attention.map((row) => row.id)).toEqual(["stopped", "broke"]);
    expect(lists.active.map((row) => row.id)).toEqual(["going", "waiting"]);
    // A run that failed and was resumed to success is finished, not attention.
    expect(lists.finished.map((row) => row.id)).toEqual(["resumed", "ok-new"]);
  });
});
