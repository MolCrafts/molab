/**
 * The cross-workspace fan-out merge: workspace attribution and per-workspace
 * failure isolation. Pure, so it runs without the poll loop or the network.
 */

import { describe, expect, it } from "@rstest/core";
import type { WorkspaceRunRow, WorkspaceRunsResponse } from "../types";
import { mergeWorkspaceRuns } from "../useWorkspaceRuns";

const row = (id: string, createdAt: string): WorkspaceRunRow =>
  ({
    id,
    name: id,
    workspaceKey: "unset",
    path: `runs/${id}`,
    projectId: "p",
    projectName: "P",
    experimentId: "e",
    experimentName: "E",
    definitionHash: "sha256:x",
    experimentRevisionId: "rev",
    inputAssetIds: [],
    targetHint: null,
    statusSummary: { total: 1, active: 0, notStarted: false, byStatus: { succeeded: 1 } },
    parameters: {},
    createdAt,
    executions: [],
  }) satisfies WorkspaceRunRow;

const response = (
  rows: WorkspaceRunRow[],
  byStatus: Record<string, number>,
): WorkspaceRunsResponse => ({
  runs: rows,
  stats: {
    totalRuns: rows.length,
    totalExecutions: rows.length,
    activeExecutions: 0,
    byStatus,
  },
  total: rows.length,
  truncated: false,
});

describe("mergeWorkspaceRuns", () => {
  it("stamps each row with the workspace it was fetched from", () => {
    const merged = mergeWorkspaceRuns([
      { key: "lab-v3", response: response([row("a", "2026-01-02T00:00:00Z")], { succeeded: 1 }) },
      {
        key: "pot-precision",
        response: response([row("b", "2026-01-01T00:00:00Z")], { failed: 1 }),
      },
    ]);
    expect(merged.runs.map((r) => [r.id, r.workspaceKey])).toEqual([
      ["a", "lab-v3"],
      ["b", "pot-precision"],
    ]);
  });

  it("orders the merged set by createdAt desc across workspaces", () => {
    const merged = mergeWorkspaceRuns([
      { key: "w1", response: response([row("old", "2026-01-01T00:00:00Z")], {}) },
      { key: "w2", response: response([row("new", "2026-06-01T00:00:00Z")], {}) },
    ]);
    expect(merged.runs.map((r) => r.id)).toEqual(["new", "old"]);
  });

  it("keeps a run id that exists in two workspaces as two distinct rows", () => {
    const merged = mergeWorkspaceRuns([
      { key: "w1", response: response([row("run-001", "2026-01-02T00:00:00Z")], {}) },
      { key: "w2", response: response([row("run-001", "2026-01-01T00:00:00Z")], {}) },
    ]);
    expect(merged.runs).toHaveLength(2);
    expect(merged.runs.map((r) => r.workspaceKey)).toEqual(["w1", "w2"]);
  });

  it("isolates a failed workspace instead of emptying the table", () => {
    const merged = mergeWorkspaceRuns([
      { key: "lab-v3", response: response([row("a", "2026-01-01T00:00:00Z")], { succeeded: 1 }) },
      { key: "remote-a", response: null },
    ]);
    expect(merged.runs.map((r) => r.id)).toEqual(["a"]);
    expect(merged.unreachable).toEqual(["remote-a"]);
  });

  it("sums status counts across workspaces", () => {
    const merged = mergeWorkspaceRuns([
      {
        key: "w1",
        response: response([row("a", "2026-01-01T00:00:00Z")], { succeeded: 2, failed: 1 }),
      },
      { key: "w2", response: response([row("b", "2026-01-01T00:00:00Z")], { succeeded: 3 }) },
    ]);
    expect(merged.stats.byStatus).toEqual({ succeeded: 5, failed: 1 });
    expect(merged.stats.totalRuns).toBe(2);
  });

  it("returns an empty set, not a throw, when every workspace failed", () => {
    const merged = mergeWorkspaceRuns([
      { key: "w1", response: null },
      { key: "w2", response: null },
    ]);
    expect(merged.runs).toEqual([]);
    expect(merged.unreachable).toEqual(["w1", "w2"]);
  });
});
