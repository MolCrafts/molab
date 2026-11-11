import { describe, expect, it } from "@rstest/core";
import type { HistoryFact } from "@/api/history";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { factStatus, factTitle, groupFactsByDay } from "./historyFacts";

const fact = (over: Partial<HistoryFact>): HistoryFact => ({
  commit: "c1",
  event: "execution.succeeded",
  subjectType: "execution",
  subjectId: "e-1",
  summary: "Catalyst Sweep · batch_size=16_ligand=L2 · succeeded",
  occurredAt: "2026-11-09T15:00:00",
  ...over,
});

const run = {
  id: "r1",
  name: "batch_size=16_ligand=L2",
  title: "L2 · 16",
  experimentId: "x",
  experimentName: "Catalyst Sweep",
  executions: [{ executionId: "e-1" }],
} as unknown as WorkspaceRunRow;

describe("historyFacts", () => {
  it("reads a status from the event", () => {
    expect(factStatus("execution.failed")).toBe("failed");
    expect(factStatus("asset.registered")).toBeNull();
  });

  it("names an attempt by experiment and run title, else the summary", () => {
    expect(factTitle(fact({}), [run])).toBe("Catalyst Sweep · L2 · 16");
    expect(factTitle(fact({ subjectId: "e-9" }), [run])).toBe(
      "Catalyst Sweep · batch_size=16_ligand=L2 · succeeded",
    );
  });

  it("groups newest first by day", () => {
    const now = new Date(2026, 10, 9, 18, 0);
    const days = groupFactsByDay(
      [
        fact({ commit: "a", occurredAt: new Date(2026, 10, 8, 10, 0).toISOString() }),
        fact({ commit: "b", occurredAt: new Date(2026, 10, 9, 15, 0).toISOString() }),
        fact({ commit: "c", occurredAt: new Date(2026, 10, 9, 9, 0).toISOString() }),
      ],
      [run],
      now,
    );
    expect(days.map((day) => day.label)).toEqual(["Today", "Yesterday"]);
    expect(days[0]?.facts.map((item) => item.key.slice(0, 1))).toEqual(["b", "c"]);
  });
});
