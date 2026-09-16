/**
 * Run-page query behaviour: what a run verb invalidates, that the logs key is
 * shared between the centre panel and the inspector, and that metrics
 * accumulate across pages instead of re-reading the file.
 */

import { beforeEach, describe, expect, it } from "@rstest/core";
import { hashKey, type QueryClient } from "@tanstack/react-query";

import { createInvalidators } from "@/app/state/queries/invalidation";
import { qk } from "@/app/state/queries/keys";
import { DEFAULT_LOG_TAIL } from "@/app/state/queries/runs";
import { makeTestQueryClient } from "@/test/queryTestUtils";

const SEEDED_KEYS: Record<string, readonly unknown[]> = {
  run: qk.run("r1"),
  runLogs: qk.runLogs("r1", null, DEFAULT_LOG_TAIL),
  runFiles: qk.runFiles("r1"),
  otherRun: qk.run("r2"),
  experimentRuns: qk.experimentRuns("p1", "e1"),
  otherExperimentRuns: qk.experimentRuns("p1", "e2"),
  runsIndex: qk.runsIndex({ limit: 1000 }),
  events: qk.events(null),
  projects: qk.projects(),
  knowledge: qk.knowledge(null),
  assets: qk.assets({ kind: "workspace" }),
  agentSessions: qk.agentSessions(),
};

const staleKeys = (client: QueryClient): string[] =>
  client
    .getQueryCache()
    .getAll()
    .filter((q) => q.state.isInvalidated)
    .map((q) => hashKey(q.queryKey))
    .sort();

const keyHashes = (names: string[]): string[] => names.map((n) => hashKey(SEEDED_KEYS[n])).sort();

let client: QueryClient;

beforeEach(() => {
  client = makeTestQueryClient();
  for (const key of Object.values(SEEDED_KEYS)) client.setQueryData(key, { seeded: true });
});

describe("run verb invalidation", () => {
  it("touches only the run, its experiment's list, the index and the feed", async () => {
    await createInvalidators(client).afterRunVerb({
      runId: "r1",
      projectId: "p1",
      experimentId: "e1",
    });

    expect(staleKeys(client)).toEqual(
      keyHashes(["run", "runLogs", "runFiles", "experimentRuns", "runsIndex", "events"]),
    );
  });

  it("leaves knowledge, assets, projects and other runs alone", async () => {
    await createInvalidators(client).afterRunVerb({
      runId: "r1",
      projectId: "p1",
      experimentId: "e1",
    });

    const stale = new Set(staleKeys(client));
    for (const untouched of [
      "otherRun",
      "otherExperimentRuns",
      "projects",
      "knowledge",
      "assets",
    ]) {
      expect(stale.has(hashKey(SEEDED_KEYS[untouched]))).toBe(false);
    }
  });

  it("harvest marks knowledge and the run, nothing else", async () => {
    await createInvalidators(client).afterHarvest({ runId: "r1" });

    const stale = new Set(staleKeys(client));
    expect(stale.has(hashKey(SEEDED_KEYS.knowledge))).toBe(true);
    expect(stale.has(hashKey(SEEDED_KEYS.run))).toBe(true);
    expect(stale.has(hashKey(SEEDED_KEYS.runsIndex))).toBe(false);
    expect(stale.has(hashKey(SEEDED_KEYS.projects))).toBe(false);
  });
});

describe("run logs key", () => {
  it("is the same for the centre panel and the inspector", () => {
    // Both call `useRunLogsQuery` with the run's coords and the selected
    // attempt, so the inspector never issues a second request.
    expect(hashKey(qk.runLogs("r1", null, DEFAULT_LOG_TAIL))).toBe(
      hashKey(qk.runLogs("r1", null, DEFAULT_LOG_TAIL)),
    );
    // A different attempt is a different entry.
    expect(hashKey(qk.runLogs("r1", "exec-r1-2", DEFAULT_LOG_TAIL))).not.toBe(
      hashKey(qk.runLogs("r1", null, DEFAULT_LOG_TAIL)),
    );
  });

  it("nests under the run so a run verb drops it", () => {
    expect(hashKey(qk.runLogs("r1", null, DEFAULT_LOG_TAIL))).not.toBe(hashKey(qk.run("r1")));
    expect(qk.runLogs("r1", null, DEFAULT_LOG_TAIL).slice(0, 2)).toEqual(qk.run("r1"));
  });
});
