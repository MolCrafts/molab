/**
 * Query-key factory contract: the hierarchy that makes prefix invalidation
 * safe. If a key moves out from under its family, targeted invalidation
 * silently stops covering it — these cases pin the containment.
 */

import { describe, expect, it } from "@rstest/core";
import { hashKey } from "@tanstack/react-query";
import { CROSS_WORKSPACE_ROOTS, isKeyPrefix, qk } from "@/app/state/queries/keys";

describe("qk", () => {
  it("nests every run sub-resource under qk.run(id)", () => {
    const run = qk.run("r1");
    for (const key of [
      qk.runLogs("r1", null, 1024),
      qk.runLogs("r1", "exec-r1-2", 4096),
      qk.runExecution("r1", null),
      qk.runFiles("r1"),
      qk.runAssets("r1"),
      qk.runMetrics("r1"),
      qk.runFileWindow("r1", "out.txt", { tail: 256 }),
    ]) {
      expect(isKeyPrefix(run, key), hashKey(key)).toBe(true);
    }
    expect(isKeyPrefix(run, qk.runFiles("r2"))).toBe(false);
  });

  it("nests experiments and their runs under the project", () => {
    expect(isKeyPrefix(["projects", "p1"], qk.experiments("p1"))).toBe(true);
    expect(isKeyPrefix(["projects", "p1"], qk.experimentRuns("p1", "e1"))).toBe(true);
    expect(isKeyPrefix(qk.projects(), qk.projectsFor("ws1"))).toBe(true);
    expect(isKeyPrefix(["projects", "p1"], qk.experiments("p2"))).toBe(false);
  });

  it("keeps the runs index outside the run and project families", () => {
    const index = qk.runsIndex({ status: "running" });
    expect(isKeyPrefix(qk.run("r1"), index)).toBe(false);
    expect(isKeyPrefix(qk.projects(), index)).toBe(false);
    expect(index[0]).toBe("runs-index");
  });

  it("groups knowledge, agent and asset families under one root each", () => {
    for (const key of [
      qk.knowledge(null),
      qk.knowledgeNote("a/b"),
      qk.knowledgeBacklinks("a/b"),
      qk.knowledgeSearch("q"),
    ]) {
      expect(isKeyPrefix(["knowledge"], key)).toBe(true);
    }
    for (const key of [qk.agentSessions(), qk.agentSession("s1"), qk.agentHealth()]) {
      expect(isKeyPrefix(["agent"], key)).toBe(true);
    }
    expect(isKeyPrefix(qk.asset("a1"), qk.assetLineage("a1"))).toBe(true);
    expect(isKeyPrefix(qk.asset("a1"), qk.assetContent("a1", "full"))).toBe(true);
    expect(isKeyPrefix(["assets"], qk.asset("a1"))).toBe(false);
  });

  it("keeps the cross-workspace keys outside every workspace family", () => {
    expect(CROSS_WORKSPACE_ROOTS.has(qk.workspaces()[0])).toBe(true);
    expect(CROSS_WORKSPACE_ROOTS.has(qk.targets()[0])).toBe(true);
    for (const key of [qk.info(), qk.projects(), qk.runsIndex(null), qk.approvals()]) {
      expect(CROSS_WORKSPACE_ROOTS.has(key[0])).toBe(false);
    }
  });

  it("hashes filter objects independently of key order", () => {
    expect(hashKey(qk.runsIndex({ a: 1, b: "x" }))).toBe(hashKey(qk.runsIndex({ b: "x", a: 1 })));
    expect(hashKey(qk.tree("", 2))).not.toBe(hashKey(qk.tree("", 1)));
  });
});
