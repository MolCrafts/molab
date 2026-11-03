import { describe, expect, it } from "@rstest/core";

import {
  attentionEdges,
  attentionMarks,
  attentionRuns,
  durationPointsOf,
  inFlightMarks,
  rollupExecutions,
  statusGroupsBy,
  varyingParameterKeys,
} from "@/app/dashboard/dashboardWidgets";
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
    inputAssetIds: [],
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
      checkpointArtifactId: null,
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

describe("durationPointsOf", () => {
  it("measures finished runs only, even when an earlier attempt has a finish time", () => {
    const rows = [
      run("finished", [done("succeeded", "2026-11-01T10:00:00Z", "2026-11-01T10:30:00Z")]),
      run("resumed", [
        done("failed", "2026-11-01T10:00:00Z", "2026-11-01T10:10:00Z"),
        { status: "running", startedAt: "2026-11-01T10:20:00Z", finishedAt: null },
      ]),
    ];
    const points = durationPointsOf(rows);
    expect(points.map((point) => point.id)).toEqual(["ws:finished"]);
    expect(points[0]?.seconds).toBe(1800);
    expect(points[0]?.status).toBe("succeeded");
  });
});

describe("attentionRuns", () => {
  it("counts runs whose latest attempt failed or was cancelled, not every failed attempt", () => {
    const rows = [
      run("recovered", [
        done("failed", "2026-11-01T10:00:00Z", "2026-11-01T10:10:00Z"),
        done("succeeded", "2026-11-01T11:00:00Z", "2026-11-01T11:10:00Z"),
      ]),
      run("broken", [done("failed", "2026-11-01T12:00:00Z", "2026-11-01T12:10:00Z")]),
      run("stopped", [done("cancelled", "2026-11-01T09:00:00Z", "2026-11-01T09:05:00Z")]),
    ];
    expect(attentionRuns(rows).map((item) => item.id)).toEqual(["broken", "stopped"]);
    // The execution rollup still sees both failed attempts.
    expect(rollupExecutions(rows).failed).toBe(2);
  });
});

describe("statusGroupsBy", () => {
  it("rolls executions up per child scope, busiest first", () => {
    const rows = [
      run("a", [done("succeeded", "2026-11-01T10:00:00Z", "2026-11-01T10:30:00Z")], {
        experimentId: "small",
      }),
      run(
        "b",
        [
          done("failed", "2026-11-01T10:00:00Z", "2026-11-01T10:10:00Z"),
          done("succeeded", "2026-11-01T11:00:00Z", "2026-11-01T11:10:00Z"),
        ],
        { experimentId: "big" },
      ),
    ];
    const groups = statusGroupsBy(rows, "experiment");
    expect(groups.map((group) => [group.id, group.counts.total])).toEqual([
      ["big", 2],
      ["small", 1],
    ]);
    expect(groups[0]?.onSelect).toBeUndefined();
  });
});

describe("instrument marks", () => {
  const now = Date.parse("2026-11-01T12:00:00Z");

  it("fills a running mark with elapsed time against twice the median", () => {
    const rows = [
      run("slow", [{ status: "running", startedAt: "2026-11-01T10:00:00Z", finishedAt: null }]),
      run("fast", [{ status: "running", startedAt: "2026-11-01T11:30:00Z", finishedAt: null }]),
      run("waiting", [{ status: "queued", startedAt: null, finishedAt: null }]),
    ];
    const marks = inFlightMarks(rows, 3600, now);
    expect(marks.map((mark) => mark.title)).toEqual([
      "slow · e1 · running 2h",
      "fast · e1 · running 30m",
      expect.stringContaining("waiting · e1 · queued"),
    ]);
    expect(marks[0]?.level).toBe(1);
    expect(marks[1]?.level).toBe(0.25);
    expect(marks[2]?.level).toBeUndefined();
  });

  it("names each run that needs attention with its age, newest first", () => {
    const rows = [
      run("old", [done("failed", "2026-11-01T08:00:00Z", "2026-11-01T09:00:00Z")]),
      run("new", [done("cancelled", "2026-11-01T11:00:00Z", "2026-11-01T11:40:00Z")]),
    ];
    expect(attentionMarks(rows, now).map((mark) => mark.title)).toEqual([
      "new · cancelled 20m ago",
      "old · failed 3h ago",
    ]);
    expect(attentionEdges(rows, now)).toEqual(["20m", "3h ago"]);
  });
});

describe("varyingParameterKeys", () => {
  it("keeps only parameters whose value differs between runs", () => {
    const a = run("a", []);
    const b = run("b", []);
    const rows = [
      { ...a, parameters: { lr: 0.1, seed: 1, precision: "fp16" } },
      { ...b, parameters: { lr: 0.2, seed: 1, precision: "fp16" } },
    ];
    expect(varyingParameterKeys(rows)).toEqual(["lr"]);
    expect(varyingParameterKeys([rows[0] as WorkspaceRunRow])).toEqual([]);
  });
});
