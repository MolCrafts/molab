/**
 * Pure-logic tests for the comparison set: ref encoding, the shortest-unique
 * label pass, and the set transitions. All run under the node environment —
 * no React, no localStorage required.
 */

import { describe, expect, it } from "@rstest/core";

import { labelAtDepth, shortestUniqueLabels, uniqueLabelDepth } from "./labels";
import { type CompareEntry, type RunRef, refKey } from "./types";
import {
  addEntries,
  parseStoredEntries,
  removeEntry,
  setEntriesSelected,
  setEntryExecution,
} from "./useCompareSet";

const ref = (
  workspaceKey: string,
  projectId: string,
  experimentId: string,
  runId: string,
): RunRef => ({
  workspaceKey,
  projectId,
  experimentId,
  runId,
});

const entry = (
  r: RunRef,
  names: { ws?: string; project?: string; experiment?: string; run?: string } = {},
  parameters: Record<string, unknown> = {},
): CompareEntry => ({
  ref: r,
  selected: true,
  executionId: null,
  workspaceLabel: names.ws ?? r.workspaceKey,
  projectName: names.project ?? r.projectId,
  experimentName: names.experiment ?? r.experimentId,
  runName: names.run ?? r.runId,
  parameters,
  addedAt: "2026-09-06T00:00:00.000Z",
});

describe("refKey", () => {
  it("is stable across calls for the same ref", () => {
    const r = ref("lab-v3", "peo-polar-length", "n-series", "n=8");
    expect(refKey(r)).toBe(refKey({ ...r }));
  });

  it("keeps four segments even when ids contain a slash", () => {
    // Ids may legally contain `/` in a hand-authored workspace; percent-encoding
    // is what stops one id from bleeding into the next segment.
    expect(refKey(ref("lab-v3", "a/b", "c/d", "e/f")).split("/")).toHaveLength(4);
  });

  it("distinguishes the same run id in two workspaces", () => {
    expect(refKey(ref("lab-v3", "p", "e", "run-001"))).not.toBe(
      refKey(ref("pot-precision", "p", "e", "run-001")),
    );
  });

  it("distinguishes ids that differ only in where the slash falls", () => {
    expect(refKey(ref("w", "a/b", "c", "d"))).not.toBe(refKey(ref("w", "a", "b/c", "d")));
  });
});

describe("uniqueLabelDepth", () => {
  it("stops at the run name when run names already differ", () => {
    const entries = [
      entry(ref("lab-v3", "p", "e", "r1"), { run: "n=8" }),
      entry(ref("lab-v3", "p", "e", "r2"), { run: "n=12" }),
    ];
    expect(uniqueLabelDepth(entries)).toBe(1);
    expect(labelAtDepth(entries[0], 1)).toBe("n=8");
  });

  it("grows to the experiment when run names collide across experiments", () => {
    const entries = [
      entry(ref("lab-v3", "p", "e1", "r1"), { run: "run-001", experiment: "n-series" }),
      entry(ref("lab-v3", "p", "e2", "r2"), { run: "run-001", experiment: "t-series" }),
    ];
    expect(uniqueLabelDepth(entries)).toBe(2);
    expect(labelAtDepth(entries[0], 2)).toBe("n-series/run-001");
  });

  it("grows to the workspace when every inner level collides", () => {
    const entries = [
      entry(ref("lab-v3", "p", "e", "r"), { ws: "lab-v3" }),
      entry(ref("pot-precision", "p", "e", "r"), { ws: "pot-precision" }),
    ];
    expect(uniqueLabelDepth(entries)).toBe(4);
    expect(labelAtDepth(entries[1], 4)).toBe("pot-precision/p/e/r");
  });

  it("applies one uniform depth across the whole set", () => {
    const entries = [
      entry(ref("lab-v3", "p", "e1", "r1"), { run: "run-001", experiment: "n-series" }),
      entry(ref("lab-v3", "p", "e2", "r2"), { run: "run-001", experiment: "t-series" }),
      entry(ref("lab-v3", "p", "e3", "r3"), { run: "unique-name", experiment: "z-series" }),
    ];
    const labels = shortestUniqueLabels(entries);
    // The third run needs no disambiguation on its own, but shares the depth
    // so the legend reads as one list rather than two kinds of thing.
    expect(labels.get(refKey(entries[2].ref))).toBe("z-series/unique-name");
  });
});

describe("set transitions", () => {
  const a = entry(ref("lab-v3", "p", "e", "r1"));
  const b = entry(ref("lab-v3", "p", "e", "r2"));
  const c = entry(ref("pot-precision", "p2", "e2", "r3"));

  it("adds across workspaces, preserving insertion order", () => {
    const next = addEntries(addEntries([], [a, b]), [c]);
    expect(next.map((e) => e.ref.runId)).toEqual(["r1", "r2", "r3"]);
  });

  it("ignores a re-add and keeps the original array identity", () => {
    const first = addEntries([], [a, b]);
    const second = addEntries(first, [a]);
    expect(second).toBe(first);
  });

  it("dedupes within a single addMany batch", () => {
    expect(addEntries([], [a, a, b])).toHaveLength(2);
  });

  it("removes by key and no-ops on an absent key", () => {
    const set = addEntries([], [a, b]);
    expect(removeEntry(set, refKey(a.ref)).map((e) => e.ref.runId)).toEqual(["r2"]);
    expect(removeEntry(set, "nope/nope/nope/nope")).toBe(set);
  });

  it("pins an execution without touching siblings", () => {
    const set = addEntries([], [a, b]);
    const next = setEntryExecution(set, refKey(a.ref), "e02");
    expect(next[0].executionId).toBe("e02");
    expect(next[1]).toBe(set[1]);
  });
});

describe("parseStoredEntries", () => {
  it("returns an empty set for null, junk, or a non-array", () => {
    expect(parseStoredEntries(null)).toEqual([]);
    expect(parseStoredEntries("{not json")).toEqual([]);
    expect(parseStoredEntries('{"a":1}')).toEqual([]);
  });

  it("drops malformed entries but keeps the valid ones", () => {
    const raw = JSON.stringify([{ ref: { workspaceKey: "w" } }, entry(ref("w", "p", "e", "r"))]);
    const parsed = parseStoredEntries(raw);
    expect(parsed).toHaveLength(1);
    expect(parsed[0].ref.runId).toBe("r");
  });

  it("backfills fields a older stored shape did not carry", () => {
    const raw = JSON.stringify([{ ref: ref("w", "p", "e", "r") }]);
    const [restored] = parseStoredEntries(raw);
    expect(restored.executionId).toBeNull();
    expect(restored.parameters).toEqual({});
    expect(restored.runName).toBe("r");
  });
});

describe("setEntriesSelected", () => {
  const staged = [
    entry(ref("w", "p", "e", "r1")),
    entry(ref("w", "p", "e", "r2")),
    entry(ref("w", "q", "e", "r3")),
  ];

  it("toggles only the named subset", () => {
    const next = setEntriesSelected(staged, new Set(["w/p/e/r1", "w/p/e/r2"]), false);
    expect(next.map((e) => e.selected)).toEqual([false, false, true]);
  });

  it("returns the same array when nothing changes", () => {
    // Identity is the store's change signal: a no-op tick must not write the
    // set to localStorage or wake every subscriber.
    expect(setEntriesSelected(staged, new Set(["w/q/e/r3"]), true)).toBe(staged);
    expect(setEntriesSelected(staged, new Set<string>(), false)).toBe(staged);
  });
});
