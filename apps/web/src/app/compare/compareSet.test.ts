/**
 * Pure-logic tests for the comparison bag: ref encoding, merge, persist,
 * reorder, and category. Node environment — no React required.
 */

import { describe, expect, it } from "@rstest/core";

import { disambiguator, labelAtDepth, shortestUniqueLabels, uniqueLabelDepth } from "./labels";
import {
  type CompareEntry,
  type CompareItem,
  type CompareRef,
  itemKey,
  type RunRef,
  refKey,
} from "./types";
import {
  addEntries,
  mergeIntoBag,
  parseStoredEntries,
  removeEntry,
  reorderItems,
  SubtreeNotLoadedError,
  setEntryExecution,
  setItemCategory,
} from "./useCompareSet";

const runRef = (
  workspaceKey: string,
  projectId: string,
  experimentId: string,
  runId: string,
): RunRef => ({ workspaceKey, projectId, experimentId, runId });

const runItem = (
  r: RunRef,
  names: { ws?: string; project?: string; experiment?: string; run?: string } = {},
  parameters: Record<string, unknown> = {},
): CompareItem => ({
  ref: { kind: "run", ...r },
  executionId: null,
  workspaceLabel: names.ws ?? r.workspaceKey,
  projectName: names.project ?? r.projectId,
  experimentName: names.experiment ?? r.experimentId,
  runName: names.run ?? r.runId,
  parameters,
  category: null,
  addedAt: "2026-09-06T00:00:00.000Z",
});

const projectItem = (workspaceKey: string, projectId: string, name?: string): CompareItem => ({
  ref: { kind: "project", workspaceKey, projectId },
  executionId: null,
  workspaceLabel: workspaceKey,
  projectName: name ?? projectId,
  experimentName: "",
  runName: "",
  parameters: {},
  category: null,
  addedAt: "2026-09-06T00:00:00.000Z",
});

const experimentItem = (
  workspaceKey: string,
  projectId: string,
  experimentId: string,
): CompareItem => ({
  ref: { kind: "experiment", workspaceKey, projectId, experimentId },
  executionId: null,
  workspaceLabel: workspaceKey,
  projectName: projectId,
  experimentName: experimentId,
  runName: "",
  parameters: {},
  category: null,
  addedAt: "2026-09-06T00:00:00.000Z",
});

const asEntry = (item: CompareItem): CompareEntry => ({
  ref: runRef(
    item.ref.workspaceKey,
    item.ref.projectId,
    item.ref.kind === "run" ? item.ref.experimentId : "",
    item.ref.kind === "run" ? item.ref.runId : "",
  ),
  executionId: item.executionId,
  workspaceLabel: item.workspaceLabel,
  projectName: item.projectName,
  experimentName: item.experimentName,
  runName: item.runName,
  parameters: item.parameters,
  addedAt: item.addedAt,
});

describe("refKey", () => {
  it("is stable across calls for the same ref", () => {
    const r = runRef("lab-v3", "peo-polar-length", "n-series", "n=8");
    expect(refKey(r)).toBe(refKey({ ...r }));
  });

  it("keeps four segments even when ids contain a slash", () => {
    expect(refKey(runRef("lab-v3", "a/b", "c/d", "e/f")).split("/")).toHaveLength(4);
  });

  it("distinguishes the same run id in two workspaces", () => {
    expect(refKey(runRef("lab-v3", "p", "e", "run-001"))).not.toBe(
      refKey(runRef("pot-precision", "p", "e", "run-001")),
    );
  });

  it("distinguishes ids that differ only in where the slash falls", () => {
    expect(refKey(runRef("w", "a/b", "c", "d"))).not.toBe(refKey(runRef("w", "a", "b/c", "d")));
  });
});

describe("itemKey", () => {
  it("uses 2/3/4 encoded segments for project/experiment/run", () => {
    expect(itemKey({ kind: "project", workspaceKey: "lab-v3", projectId: "peo-tg" })).toBe(
      "lab-v3/peo-tg",
    );
    expect(
      itemKey({
        kind: "experiment",
        workspaceKey: "lab-v3",
        projectId: "peo-tg",
        experimentId: "n-series",
      }).split("/"),
    ).toHaveLength(3);
    expect(
      itemKey({
        kind: "run",
        workspaceKey: "lab-v3",
        projectId: "p",
        experimentId: "e",
        runId: "r",
      }).split("/"),
    ).toHaveLength(4);
  });

  it("distinguishes the same projectId in two workspaceKeys", () => {
    const a: CompareRef = { kind: "project", workspaceKey: "lab-v3", projectId: "peo-tg" };
    const b: CompareRef = { kind: "project", workspaceKey: "pot", projectId: "peo-tg" };
    expect(itemKey(a)).not.toBe(itemKey(b));
  });
});

describe("uniqueLabelDepth", () => {
  it("stops at the run name when run names already differ", () => {
    const entries = [
      asEntry(runItem(runRef("lab-v3", "p", "e", "r1"), { run: "n=8" })),
      asEntry(runItem(runRef("lab-v3", "p", "e", "r2"), { run: "n=12" })),
    ];
    expect(uniqueLabelDepth(entries)).toBe(1);
    expect(labelAtDepth(entries[0], 1)).toBe("n=8");
  });

  it("grows to the experiment when run names collide across experiments", () => {
    const entries = [
      asEntry(
        runItem(runRef("lab-v3", "p", "e1", "r1"), { run: "run-001", experiment: "n-series" }),
      ),
      asEntry(
        runItem(runRef("lab-v3", "p", "e2", "r2"), { run: "run-001", experiment: "t-series" }),
      ),
    ];
    expect(uniqueLabelDepth(entries)).toBe(2);
    expect(labelAtDepth(entries[0], 2)).toBe("n-series · run-001");
  });

  it("grows to the workspace when every inner level collides", () => {
    const entries = [
      asEntry(runItem(runRef("lab-v3", "p", "e", "r"), { ws: "lab-v3" })),
      asEntry(runItem(runRef("pot-precision", "p", "e", "r"), { ws: "pot-precision" })),
    ];
    expect(uniqueLabelDepth(entries)).toBe(4);
    expect(labelAtDepth(entries[1], 4)).toBe("pot-precision · p · e · r");
  });

  it("applies one uniform depth across the whole set", () => {
    const entries = [
      asEntry(
        runItem(runRef("lab-v3", "p", "e1", "r1"), { run: "run-001", experiment: "n-series" }),
      ),
      asEntry(
        runItem(runRef("lab-v3", "p", "e2", "r2"), { run: "run-001", experiment: "t-series" }),
      ),
      asEntry(
        runItem(runRef("lab-v3", "p", "e3", "r3"), { run: "unique-name", experiment: "z-series" }),
      ),
    ];
    const labels = shortestUniqueLabels(entries);
    expect(labels.get(refKey(entries[2].ref))).toBe("z-series · unique-name");
  });

  it("names the parent entity that tells colliding run names apart", () => {
    const entries = [
      asEntry(
        runItem(runRef("lab-v3", "p", "e1", "r1"), { run: "run-001", experiment: "n-series" }),
      ),
      asEntry(
        runItem(runRef("lab-v3", "p", "e2", "r2"), { run: "run-001", experiment: "t-series" }),
      ),
    ];
    expect(disambiguator(entries[0], 1)).toBeNull();
    expect(disambiguator(entries[0], 2)).toBe("n-series");
  });
});

describe("set transitions", () => {
  const a = runItem(runRef("lab-v3", "p", "e", "r1"));
  const b = runItem(runRef("lab-v3", "p", "e", "r2"));
  const c = runItem(runRef("pot-precision", "p2", "e2", "r3"));

  it("adds across workspaces, preserving insertion order", () => {
    const next = addEntries(addEntries([], [a, b]), [c]);
    expect(next.map((e) => (e.ref.kind === "run" ? e.ref.runId : ""))).toEqual(["r1", "r2", "r3"]);
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
    expect(
      removeEntry(set, itemKey(a.ref)).map((e) => (e.ref.kind === "run" ? e.ref.runId : "")),
    ).toEqual(["r2"]);
    expect(removeEntry(set, "nope/nope/nope/nope")).toBe(set);
  });

  it("pins an execution without touching siblings", () => {
    const set = addEntries([], [a, b]);
    const next = setEntryExecution(set, itemKey(a.ref), "e02");
    expect(next[0].executionId).toBe("e02");
    expect(next[1]).toBe(set[1]);
  });
});

describe("mergeIntoBag", () => {
  const project = projectItem("lab-v3", "peo-tg");
  const n8 = runItem(runRef("lab-v3", "peo-tg", "n-series", "n=8"), { run: "n=8" });
  const n12 = runItem(runRef("lab-v3", "peo-tg", "n-series", "n=12"), { run: "n=12" });

  it("drops descendants when a project is added", () => {
    const next = mergeIntoBag([n8, n12], [project]);
    expect(next).toHaveLength(1);
    expect(next[0].ref.kind).toBe("project");
  });

  it("materializes remaining siblings when adding a run under a staged project", () => {
    const next = mergeIntoBag([project], [n8], {
      isSubtreeLoaded: () => true,
      siblingRuns: () => [n12],
    });
    expect(next.map((item) => (item.ref.kind === "run" ? item.ref.runId : item.ref.kind))).toEqual([
      "n=12",
      "n=8",
    ]);
  });

  it("throws and leaves the bag unchanged when the subtree is not loaded", () => {
    const current = [project];
    expect(() =>
      mergeIntoBag(current, [n8], {
        isSubtreeLoaded: () => false,
        siblingRuns: () => [n12],
      }),
    ).toThrow(SubtreeNotLoadedError);
    expect(mergeIntoBag.length).toBeGreaterThan(0);
    expect(current).toHaveLength(1);
  });

  it("adds mixed kinds without collapsing them", () => {
    const experiment = experimentItem("lab-v3", "other", "e");
    const otherRun = runItem(runRef("lab-v3", "third", "e", "r"));
    const next = mergeIntoBag([], [project, experiment, otherRun]);
    expect(next).toHaveLength(3);
  });
});

describe("reorderItems and setItemCategory", () => {
  const a = runItem(runRef("w", "p", "e", "a"));
  const b = runItem(runRef("w", "p", "e", "b"));
  const c = runItem(runRef("w", "p", "e", "c"));

  it("moves the first item to the end", () => {
    expect(
      reorderItems([a, b, c], 0, 2).map((item) => (item.ref.kind === "run" ? item.ref.runId : "")),
    ).toEqual(["b", "c", "a"]);
  });

  it("returns the original array identity for out-of-range or equal indexes", () => {
    const current = [a, b, c];
    expect(reorderItems(current, 0, 0)).toBe(current);
    expect(reorderItems(current, -1, 1)).toBe(current);
    expect(reorderItems(current, 0, 9)).toBe(current);
  });

  it("writes an empty category as ungrouped null", () => {
    const next = setItemCategory([a], itemKey(a.ref), null);
    expect(next[0].category).toBeNull();
  });
});

describe("parseStoredEntries", () => {
  it("returns an empty set for null, junk, or a non-array", () => {
    expect(parseStoredEntries(null)).toEqual([]);
    expect(parseStoredEntries("{not json")).toEqual([]);
    expect(parseStoredEntries('{"a":1}')).toEqual([]);
  });

  it("drops malformed entries but keeps the valid ones", () => {
    const raw = JSON.stringify([
      { ref: { workspaceKey: "w" } },
      runItem(runRef("w", "p", "e", "r")),
    ]);
    const parsed = parseStoredEntries(raw);
    expect(parsed).toHaveLength(1);
    expect(parsed[0].ref.kind).toBe("run");
  });

  it("migrates a compareSet.v1 run object without kind as run-kind with category null", () => {
    const raw = JSON.stringify([
      {
        ref: { workspaceKey: "lab-v3", projectId: "p", experimentId: "e", runId: "r" },
        selected: false,
      },
    ]);
    const [restored] = parseStoredEntries(raw);
    expect(restored.ref).toEqual({
      kind: "run",
      workspaceKey: "lab-v3",
      projectId: "p",
      experimentId: "e",
      runId: "r",
    });
    expect(restored.category).toBeNull();
    expect(restored.executionId).toBeNull();
  });
});
