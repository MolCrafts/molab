/**
 * The invalidation map is the contract between the SSE change stream / the
 * mutation helpers and the cache. Each case seeds every key family, applies
 * one change, and asserts that exactly the expected queries are stale —
 * over-invalidation would silently bring the "refresh bomb" back.
 */

import { beforeEach, describe, expect, it } from "@rstest/core";
import { hashKey, type QueryClient } from "@tanstack/react-query";
import {
  applyInvalidations,
  createInvalidators,
  invalidationsFor,
  LIST_LEVEL_INVALIDATIONS,
  parentDirOf,
  viewInvalidations,
  type WorkspaceChange,
} from "@/app/state/queries/invalidation";
import { qk } from "@/app/state/queries/keys";
import { makeTestQueryClient } from "@/test/queryTestUtils";

const SEEDED: readonly (readonly unknown[])[] = [
  qk.workspaces(),
  qk.targets(),
  qk.info(),
  qk.tree("", 2),
  qk.tree("projects/p1", 1),
  qk.fileWindow("projects/p1/a.txt", "full"),
  qk.projects(),
  qk.projectsFor("ws1"),
  qk.experiments("p1"),
  qk.experiments("p2"),
  qk.experimentRuns("p1", "e1"),
  qk.experimentRuns("p2", "e2"),
  qk.runsIndex(null),
  qk.runsIndex({ status: "running" }),
  qk.run("r1"),
  qk.runLogs("r1", null, 1024),
  qk.runFiles("r1"),
  qk.runAssets("r1"),
  qk.run("r2"),
  qk.runFiles("r2"),
  qk.assets({ kind: "workspace" }),
  qk.assets({ kind: "project", id: "p1" }),
  qk.asset("a1"),
  qk.assetLineage("a1"),
  qk.asset("a2"),
  qk.knowledge(null),
  qk.knowledgeNote("n1"),
  qk.knowledgeBacklinks("n1"),
  qk.knowledgeSearch("q"),
  qk.events(null),
  qk.agentSessions(),
  qk.agentSession("s1"),
  qk.agentSession("s2"),
  qk.agentHealth(),
  qk.plan("p1", "e1", "r1"),
  qk.curateTask("p1", "e1", "t1"),
  qk.approvals(),
];

const seed = (client: QueryClient): void => {
  for (const key of SEEDED) client.setQueryData(key, { seeded: true });
};

const staleKeys = (client: QueryClient): Set<string> =>
  new Set(
    client
      .getQueryCache()
      .getAll()
      .filter((query) => query.state.isInvalidated)
      .map((query) => hashKey(query.queryKey)),
  );

const presentKeys = (client: QueryClient): Set<string> =>
  new Set(
    client
      .getQueryCache()
      .getAll()
      .map((query) => hashKey(query.queryKey)),
  );

const expectStaleExactly = (client: QueryClient, expected: readonly (readonly unknown[])[]) => {
  expect([...staleKeys(client)].sort()).toEqual(expected.map(hashKey).sort());
};

const apply = (client: QueryClient, change: WorkspaceChange) =>
  applyInvalidations(client, invalidationsFor(change), { refetchType: "none" });

let client: QueryClient;

beforeEach(() => {
  client = makeTestQueryClient();
  seed(client);
});

describe("invalidationsFor", () => {
  it("run: the run's family, its experiment list, the runs index and events", async () => {
    await apply(client, { kind: "run", ref: "r1", seq: 1, projectId: "p1", experimentId: "e1" });
    expectStaleExactly(client, [
      qk.run("r1"),
      qk.runLogs("r1", null, 1024),
      qk.runFiles("r1"),
      qk.runAssets("r1"),
      qk.experimentRuns("p1", "e1"),
      qk.runsIndex(null),
      qk.runsIndex({ status: "running" }),
      qk.events(null),
    ]);
  });

  it("run without coordinates: every experiment-runs list, no other project keys", async () => {
    await apply(client, { kind: "run", ref: "r2", seq: 2 });
    expectStaleExactly(client, [
      qk.run("r2"),
      qk.runFiles("r2"),
      qk.experimentRuns("p1", "e1"),
      qk.experimentRuns("p2", "e2"),
      qk.runsIndex(null),
      qk.runsIndex({ status: "running" }),
      qk.events(null),
    ]);
  });

  it("asset: asset lists, that asset, its run's assets/files and the tree", async () => {
    await apply(client, { kind: "asset", ref: "a1", seq: 3, runId: "r1" });
    expectStaleExactly(client, [
      qk.assets({ kind: "workspace" }),
      qk.assets({ kind: "project", id: "p1" }),
      qk.asset("a1"),
      qk.assetLineage("a1"),
      qk.runAssets("r1"),
      qk.runFiles("r1"),
      qk.tree("", 2),
      qk.tree("projects/p1", 1),
    ]);
  });

  it("knowledge: the whole knowledge family and nothing else", async () => {
    await apply(client, { kind: "knowledge", ref: "n1", seq: 4 });
    expectStaleExactly(client, [
      qk.knowledge(null),
      qk.knowledgeNote("n1"),
      qk.knowledgeBacklinks("n1"),
      qk.knowledgeSearch("q"),
    ]);
  });

  it("project: the project list, that project's subtree and the root tree", async () => {
    await apply(client, { kind: "project", ref: "p1", seq: 5 });
    expectStaleExactly(client, [
      qk.projects(),
      qk.projectsFor("ws1"),
      qk.experiments("p1"),
      qk.experimentRuns("p1", "e1"),
      qk.tree("", 2),
    ]);
  });

  it("experiment: that experiment, its runs list, project counts and the root tree", async () => {
    await apply(client, { kind: "experiment", ref: "e1", seq: 6, projectId: "p1" });
    expectStaleExactly(client, [
      qk.experiments("p1"),
      qk.experimentRuns("p1", "e1"),
      qk.projects(),
      qk.tree("", 2),
    ]);
  });

  it("workspace with a path: info, the parent listing and that file", async () => {
    await apply(client, { kind: "workspace", ref: "projects/p1/a.txt", seq: 7 });
    expectStaleExactly(client, [
      qk.info(),
      qk.tree("projects/p1", 1),
      qk.fileWindow("projects/p1/a.txt", "full"),
    ]);
  });

  it("workspace without a path: info and every tree listing", async () => {
    await apply(client, { kind: "workspace", ref: null, seq: 8 });
    expectStaleExactly(client, [qk.info(), qk.tree("", 2), qk.tree("projects/p1", 1)]);
  });

  it("agent: the session list and that session only", async () => {
    await apply(client, { kind: "agent", ref: "s1", seq: 9 });
    expectStaleExactly(client, [qk.agentSessions(), qk.agentSession("s1")]);
  });

  it("approval: the approvals inbox only", async () => {
    await apply(client, { kind: "approval", ref: null, seq: 10 });
    expectStaleExactly(client, [qk.approvals()]);
  });

  it("all: everything except the cross-workspace keys", async () => {
    await apply(client, { kind: "all", ref: null, seq: 11 });
    const stale = staleKeys(client);
    expect(stale.has(hashKey(qk.workspaces()))).toBe(false);
    expect(stale.has(hashKey(qk.targets()))).toBe(false);
    expect(stale.size).toBe(SEEDED.length - 2);
  });

  it("list-level fallback covers the navigator lists, not detail keys", async () => {
    await applyInvalidations(client, LIST_LEVEL_INVALIDATIONS, { refetchType: "none" });
    const stale = staleKeys(client);
    for (const key of [qk.info(), qk.projects(), qk.runsIndex(null), qk.agentSessions()]) {
      expect(stale.has(hashKey(key)), hashKey(key)).toBe(true);
    }
    for (const key of [qk.run("r1"), qk.experiments("p1"), qk.agentSession("s1")]) {
      expect(stale.has(hashKey(key)), hashKey(key)).toBe(false);
    }
  });
});

describe("createInvalidators", () => {
  it("afterRunVerb touches only the run, its experiment list, the index and events", async () => {
    await createInvalidators(client).afterRunVerb({
      runId: "r1",
      projectId: "p1",
      experimentId: "e1",
    });
    expectStaleExactly(client, [
      qk.run("r1"),
      qk.runLogs("r1", null, 1024),
      qk.runFiles("r1"),
      qk.runAssets("r1"),
      qk.experimentRuns("p1", "e1"),
      qk.runsIndex(null),
      qk.runsIndex({ status: "running" }),
      qk.events(null),
    ]);
  });

  it("afterProjectDelete removes the project subtree and stales the lists", async () => {
    await createInvalidators(client).afterProjectDelete({ projectId: "p1" });
    const present = presentKeys(client);
    expect(present.has(hashKey(qk.experiments("p1")))).toBe(false);
    expect(present.has(hashKey(qk.experimentRuns("p1", "e1")))).toBe(false);
    expect(present.has(hashKey(qk.experiments("p2")))).toBe(true);
    expectStaleExactly(client, [
      qk.projects(),
      qk.projectsFor("ws1"),
      qk.runsIndex(null),
      qk.runsIndex({ status: "running" }),
      qk.assets({ kind: "workspace" }),
      qk.assets({ kind: "project", id: "p1" }),
      qk.tree("", 2),
    ]);
  });

  it("afterFsWrite stales only the parent directory listing", async () => {
    await createInvalidators(client).afterFsWrite("projects/p1/new.txt");
    expectStaleExactly(client, [qk.tree("projects/p1", 1)]);
  });

  it("afterWorkspaceSwitch keeps only the cross-workspace keys", async () => {
    await createInvalidators(client).afterWorkspaceSwitch();
    expect([...presentKeys(client)].sort()).toEqual(
      [hashKey(qk.workspaces()), hashKey(qk.targets())].sort(),
    );
  });

  it("invalidateView('runs') stales the runs index and events only", async () => {
    await createInvalidators(client).invalidateView("runs");
    expectStaleExactly(client, [
      qk.runsIndex(null),
      qk.runsIndex({ status: "running" }),
      qk.events(null),
    ]);
  });

  it("agent-task open has no invalidation helper (nothing to invalidate)", () => {
    const helpers = createInvalidators(client) as unknown as Record<string, unknown>;
    expect(helpers.afterAgentOpen).toBeUndefined();
  });
});

describe("helpers", () => {
  it("parentDirOf returns the workspace-relative parent, '' at the root", () => {
    expect(parentDirOf("a.txt")).toBe("");
    expect(parentDirOf("projects/p1/a.txt")).toBe("projects/p1");
    expect(parentDirOf("projects/p1/")).toBe("projects");
  });

  it("viewInvalidations covers every navigator view", () => {
    for (const view of [
      "workspace",
      "projects",
      "runs",
      "asset",
      "workflow",
      "agent",
      "knowledge",
      "settings",
    ] as const) {
      expect(viewInvalidations(view).length, view).toBeGreaterThan(0);
    }
  });
});
