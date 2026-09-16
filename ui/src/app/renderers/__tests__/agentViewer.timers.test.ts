/**
 * Agent polling decisions.
 *
 * These are the pure functions the session/plan queries hand to
 * `refetchInterval`. They are tested directly rather than by advancing fake
 * timers: TanStack's `refetchInterval` does not fire under rstest's fake
 * timers, so a "no requests after N seconds" assertion would pass whether or
 * not the interval logic were correct. The contract test in
 * `app/state/queries/__tests__/no-raw-polling.contract.test.ts` covers the
 * other half — that no hand-rolled timer survives in the viewer at all.
 */

import { describe, expect, it } from "@rstest/core";
import {
  AGENT_SESSION_POLL_MS,
  agentSessionRefetchInterval,
  curateRefetchInterval,
  isLiveAgentStatus,
  PLAN_DECISION_GRACE_MS,
  PLAN_POLL_MS,
  planRefetchInterval,
} from "@/app/state/queries";

describe("agent session polling", () => {
  it("polls while the task is live", () => {
    for (const status of ["running", "waiting_approval", "awaiting_user"]) {
      expect(agentSessionRefetchInterval({ status })).toBe(AGENT_SESSION_POLL_MS);
    }
  });

  it("stops at a terminal status", () => {
    for (const status of ["completed", "failed", "cancelled"]) {
      expect(agentSessionRefetchInterval({ status })).toBe(false);
    }
  });

  it("stops when the query is disabled, whatever the status says", () => {
    expect(agentSessionRefetchInterval({ status: "running" }, false)).toBe(false);
  });

  it("does not poll on missing data", () => {
    expect(agentSessionRefetchInterval(undefined)).toBe(false);
  });

  it("classifies live statuses", () => {
    expect(isLiveAgentStatus("running")).toBe(true);
    expect(isLiveAgentStatus("completed")).toBe(false);
    expect(isLiveAgentStatus(null)).toBe(false);
    expect(isLiveAgentStatus(undefined)).toBe(false);
  });
});

describe("plan artifact polling", () => {
  it("polls while the session is live", () => {
    expect(planRefetchInterval("running", null)).toBe(PLAN_POLL_MS);
  });

  it("keeps polling briefly after a decision while realization finishes", () => {
    const now = 10_000_000;
    expect(planRefetchInterval("completed", now - 1_000, now)).toBe(PLAN_POLL_MS);
  });

  it("stops once the post-decision grace window elapses", () => {
    // The predicate this replaces (`planRefreshKey > 0`) could never return to
    // false once bumped, so the 2s poll ran for the rest of the session.
    const now = 10_000_000;
    expect(planRefetchInterval("completed", now - PLAN_DECISION_GRACE_MS - 1, now)).toBe(false);
  });

  it("stops for a calm session that never had a decision", () => {
    expect(planRefetchInterval("completed", null)).toBe(false);
  });
});

describe("curate polling", () => {
  it("polls while running or awaiting approval", () => {
    expect(curateRefetchInterval({ status: "running" })).not.toBe(false);
    expect(curateRefetchInterval({ status: "waiting_approval" })).not.toBe(false);
  });

  it("stops once the task settles", () => {
    for (const status of ["completed", "failed", "cancelled"]) {
      expect(curateRefetchInterval({ status })).toBe(false);
    }
  });
});
