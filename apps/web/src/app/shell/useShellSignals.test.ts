import { describe, expect, it } from "@rstest/core";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { attentionCount } from "./useShellSignals";

/** A run with its attempts in order, oldest first. */
const row = (id: string, statuses: readonly string[]): WorkspaceRunRow =>
  ({
    id,
    targetHint: null,
    executions: statuses.map((status, index) => ({
      executionId: `e0${index + 1}`,
      status,
      createdAt: `2026-11-01T1${index}:00:00Z`,
      backendMetadata: {},
    })),
    statusSummary: {
      total: statuses.length,
      active: 0,
      notStarted: statuses.length === 0,
      byStatus: Object.fromEntries(statuses.map((status) => [status, 1])),
    },
  }) as unknown as WorkspaceRunRow;

describe("attentionCount", () => {
  it("counts runs, not attempts: three failed attempts are one run", () => {
    expect(attentionCount([row("a", ["failed", "failed", "failed"])])).toBe(1);
  });

  it("counts failed and interrupted runs and nothing else", () => {
    const runs = [
      row("a", ["failed"]),
      row("b", ["interrupted"]),
      row("c", ["succeeded", "succeeded"]),
      row("d", ["running"]),
      row("e", ["cancelled"]),
    ];
    expect(attentionCount(runs)).toBe(2);
  });

  it("does not count a run that failed and was resumed to success", () => {
    expect(attentionCount([row("a", ["failed", "succeeded"])])).toBe(0);
  });

  it("is zero for a workspace with nothing to report", () => {
    expect(attentionCount([])).toBe(0);
    expect(attentionCount(undefined)).toBe(0);
  });
});
