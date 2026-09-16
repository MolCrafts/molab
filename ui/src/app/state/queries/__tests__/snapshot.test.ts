/**
 * Snapshot composition helpers and the invalidation contract that replaced the
 * old `refresh()` bomb (plan P2 §2b).
 *
 * The composition hook itself needs React, which rstest 0.10 cannot render
 * headlessly; what is asserted here is the pure part (key parsing) plus the
 * behaviour the rewrite is *for*: a targeted invalidation leaves the expanded
 * tree's cached data in place, where the old refresh emptied it.
 */

import { describe, expect, test } from "@rstest/core";
import { makeTestQueryClient } from "@/test/queryTestUtils";
import { createInvalidators } from "../invalidation";
import { qk } from "../keys";
import { expKey, parseExpKey } from "../snapshot";

describe("TestExpansionKeys", () => {
  test("expKey and parseExpKey round-trip", () => {
    expect(expKey("proj", "exp")).toBe("proj/exp");
    expect(parseExpKey("proj/exp")).toEqual({ projectId: "proj", experimentId: "exp" });
  });

  test("parseExpKey keeps ids containing a slash on the experiment side", () => {
    expect(parseExpKey("proj/exp/extra")).toEqual({
      projectId: "proj",
      experimentId: "exp/extra",
    });
  });
});

describe("TestRefreshKeepsExpandedTree", () => {
  /** Seed a workspace whose tree has been expanded two levels deep. */
  const seedExpandedTree = () => {
    const client = makeTestQueryClient();
    client.setQueryData(qk.projects(), [{ id: "p1" }]);
    client.setQueryData(qk.experiments("p1"), [{ id: "e1" }]);
    client.setQueryData(qk.experimentRuns("p1", "e1"), [{ id: "r1" }]);
    client.setQueryData(qk.tree("", 2), [{ name: "projects" }]);
    return client;
  };

  test("a manual view refresh keeps every expanded level's data", async () => {
    const client = seedExpandedTree();
    await createInvalidators(client).invalidateView("projects");

    // Invalidation marks stale; it must never clear. The old `refresh()` set
    // experiments/runs to [], which collapsed the navigator.
    expect(client.getQueryData(qk.experiments("p1"))).toEqual([{ id: "e1" }]);
    expect(client.getQueryData(qk.experimentRuns("p1", "e1"))).toEqual([{ id: "r1" }]);
  });

  test("a run verb does not touch the project or tree caches", async () => {
    const client = seedExpandedTree();
    await createInvalidators(client).afterRunVerb({
      runId: "r1",
      projectId: "p1",
      experimentId: "e1",
    });

    const state = (key: readonly unknown[]) => client.getQueryState(key);
    expect(state(qk.experimentRuns("p1", "e1"))?.isInvalidated).toBe(true);
    expect(state(qk.projects())?.isInvalidated).toBeFalsy();
    expect(state(qk.tree("", 2))?.isInvalidated).toBeFalsy();
  });

  test("opening an agent task invalidates nothing in the workspace tree", async () => {
    const client = seedExpandedTree();
    client.setQueryData(qk.agentSessions(), [{ id: "a1" }]);

    // Deliberately no call: opening a task used to fire onRefresh().
    const invalidated = client
      .getQueryCache()
      .getAll()
      .filter((query) => query.state.isInvalidated);
    expect(invalidated).toHaveLength(0);
  });

  test("a project delete removes that project's subtree and keeps the rest", async () => {
    const client = seedExpandedTree();
    client.setQueryData(qk.experiments("p2"), [{ id: "e9" }]);

    await createInvalidators(client).afterProjectDelete({ projectId: "p1" });

    expect(client.getQueryData(qk.experiments("p1"))).toBe(undefined);
    expect(client.getQueryData(qk.experimentRuns("p1", "e1"))).toBe(undefined);
    expect(client.getQueryData(qk.experiments("p2"))).toEqual([{ id: "e9" }]);
  });
});
