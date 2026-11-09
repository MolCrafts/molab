import { describe, expect, it } from "@rstest/core";
import {
  delegationAsk,
  findApproval,
  isApprovalGate,
  isDelegationRecord,
  needsDecision,
  withApproval,
  withRejection,
} from "./delegationEdits";

const BASE = {
  goal: "Validate thermostats",
  scope: "Thermostat Validation",
  state: "blocked",
  current_plan: "Run 4 jobs on hpc-slurm",
  questions: ["Run 4 jobs?"],
};

describe("delegationAsk", () => {
  it("prefers the attribute, then the last question, the plan, the goal", () => {
    expect(delegationAsk(BASE, "Explicit")).toBe("Explicit");
    expect(delegationAsk(BASE)).toBe("Run 4 jobs?");
    expect(delegationAsk({ ...BASE, questions: [] })).toBe("Run 4 jobs on hpc-slurm");
    expect(delegationAsk({ goal: "Goal", scope: "s" })).toBe("Goal");
  });
});

describe("approvals", () => {
  const approval = { gate: "plan", target: "a.md", by: "roy", at: "2026-11-09T10:00:00Z" };
  it("appends an approval and opens the delegation, keeping other keys", () => {
    const next = withApproval(BASE, approval);
    expect(next.state).toBe("open");
    expect(next.approvals).toEqual([approval]);
    expect(next.goal).toBe(BASE.goal);
    expect(findApproval(next, "plan", "a.md")).toEqual(approval);
    expect(findApproval(next, "results", "a.md")).toBeNull();
  });
  it("rejects by pausing", () => {
    expect(withRejection(BASE)).toEqual({ ...BASE, state: "paused" });
  });
  it("needs a decision when blocked, or when a named gate has no approval", () => {
    expect(needsDecision(BASE, undefined, "a.md")).toBe(true);
    expect(needsDecision({ ...BASE, state: "open" }, undefined, "a.md")).toBe(false);
    expect(needsDecision({ ...BASE, state: "open" }, "plan", "a.md")).toBe(true);
    expect(needsDecision(withApproval(BASE, approval), "plan", "a.md")).toBe(false);
    expect(needsDecision({ ...BASE, state: "paused" }, "plan", "a.md")).toBe(false);
  });
  it("knows its gates and its shape", () => {
    expect(isApprovalGate("dry_run")).toBe(true);
    expect(isApprovalGate("ship")).toBe(false);
    expect(isDelegationRecord({})).toBe(false);
    expect(isDelegationRecord(BASE)).toBe(true);
  });
});
