/**
 * Pure-logic tests for category grouping and project → experiment → run nesting.
 */

import { describe, expect, it } from "@rstest/core";

import type { WorkspaceSnapshot } from "@/app/types";

import {
  buildCategoryGroups,
  buildComparisonTree,
  comparisonSpansWorkspaces,
  hydrateComparisonTree,
  keysUnderExperiment,
  keysUnderProject,
} from "./comparisonTree";
import type { CompareItem, RunRef } from "./types";

const ref = (
  workspaceKey: string,
  projectId: string,
  experimentId: string,
  runId: string,
): RunRef => ({ workspaceKey, projectId, experimentId, runId });

const entry = (
  r: RunRef,
  names: { ws?: string; project?: string; experiment?: string; run?: string } = {},
  category: string | null = null,
): CompareItem => ({
  ref: { kind: "run", ...r },
  executionId: null,
  workspaceLabel: names.ws ?? r.workspaceKey,
  projectName: names.project ?? r.projectId,
  experimentName: names.experiment ?? r.experimentId,
  runName: names.run ?? r.runId,
  parameters: {},
  category,
  addedAt: "2026-09-06T00:00:00.000Z",
});

describe("buildComparisonTree", () => {
  it("nests runs under their experiment and project", () => {
    const tree = buildComparisonTree([
      entry(ref("lab", "peo", "n-series", "n=8")),
      entry(ref("lab", "peo", "n-series", "n=16")),
      entry(ref("lab", "peo", "tg-fit", "dp=5")),
    ]);

    expect(tree).toHaveLength(1);
    expect(tree[0].experiments.map((e) => e.name)).toEqual(["n-series", "tg-fit"]);
    expect(tree[0].experiments[0].runs.map((r) => r.entry.runName)).toEqual(["n=8", "n=16"]);
  });

  it("keeps insertion order at every level", () => {
    const tree = buildComparisonTree([
      entry(ref("lab", "zeta", "e1", "r1")),
      entry(ref("lab", "alpha", "e2", "r2")),
      entry(ref("lab", "zeta", "e3", "r3")),
    ]);

    expect(tree.map((p) => p.name)).toEqual(["zeta", "alpha"]);
    expect(tree[0].experiments.map((e) => e.name)).toEqual(["e1", "e3"]);
  });

  it("separates same-named projects served from different workspaces", () => {
    const tree = buildComparisonTree([
      entry(ref("lab-v3", "peo", "e", "r"), { ws: "lab-v3" }),
      entry(ref("hpc", "peo", "e", "r"), { ws: "hpc" }),
    ]);

    expect(tree).toHaveLength(2);
    expect(tree.map((p) => p.workspaceLabel)).toEqual(["lab-v3", "hpc"]);
  });

  it("keeps projects whose ids share a prefix apart", () => {
    const tree = buildComparisonTree([
      entry(ref("w", "peo", "e", "r1")),
      entry(ref("w", "peo-polar", "e", "r2")),
    ]);

    expect(tree).toHaveLength(2);
  });

  it("addresses each run by its itemKey", () => {
    const tree = buildComparisonTree([entry(ref("lab", "p", "e", "r"))]);
    expect(tree[0].experiments[0].runs[0].key).toBe("lab/p/e/r");
  });

  it("collects bag keys under a project and under an experiment", () => {
    const items = [
      entry(ref("lab", "peo", "n-series", "n=8")),
      entry(ref("lab", "peo", "n-series", "n=16")),
      entry(ref("lab", "peo", "tg-fit", "dp=5")),
    ];
    const tree = buildComparisonTree(items);
    expect(keysUnderProject(items, tree[0])).toHaveLength(3);
    expect(keysUnderExperiment(items, tree[0], tree[0].experiments[0])).toHaveLength(2);
  });
});

describe("hydrateComparisonTree", () => {
  it("expands a selected project into snapshot experiments and runs", () => {
    const projectItem: CompareItem = {
      ref: { kind: "project", workspaceKey: "lab", projectId: "peo" },
      executionId: null,
      workspaceLabel: "lab",
      projectName: "peo",
      experimentName: "",
      runName: "",
      parameters: {},
      category: null,
      addedAt: "2026-09-06T00:00:00.000Z",
    };
    const snapshot = {
      experiments: [{ id: "n-series", name: "n-series", projectId: "peo", workspaceKey: "lab" }],
      runs: [
        {
          id: "n=8",
          name: "n=8",
          projectId: "peo",
          experimentId: "n-series",
          workspaceKey: "lab",
          parameters: {},
        },
      ],
    } as unknown as WorkspaceSnapshot;
    const tree = hydrateComparisonTree([projectItem], snapshot);
    expect(tree[0].experiments).toHaveLength(1);
    expect(tree[0].experiments[0].name).toBe("n-series");
    expect(tree[0].experiments[0].runs.map((run) => run.entry.runName)).toEqual(["n=8"]);
    expect(tree[0].experiments[0].runs[0].virtual).toBe(true);
  });
});

describe("comparisonSpansWorkspaces", () => {
  it("is false for one workspace and true for two", () => {
    const one = [entry(ref("lab", "p", "e", "r1")), entry(ref("lab", "q", "e", "r2"))];
    expect(comparisonSpansWorkspaces(one)).toBe(false);
    expect(comparisonSpansWorkspaces([...one, entry(ref("hpc", "p", "e", "r3"))])).toBe(true);
  });

  it("is false for an empty comparison", () => {
    expect(comparisonSpansWorkspaces([])).toBe(false);
  });
});

describe("buildCategoryGroups", () => {
  it("puts ungrouped items first and preserves bag order inside a bucket", () => {
    const items = [
      entry(ref("w", "p", "e", "a"), {}, null),
      entry(ref("w", "p", "e", "b"), {}, "seed"),
      entry(ref("w", "p", "e", "c"), {}, null),
      entry(ref("w", "p", "e", "d"), {}, "seed"),
    ];
    const groups = buildCategoryGroups(items);
    expect(groups[0].category).toBeNull();
    expect(groups[0].items.map((item) => item.runName)).toEqual(["a", "c"]);
    expect(groups[1].category).toBe("seed");
    expect(groups[1].items.map((item) => item.runName)).toEqual(["b", "d"]);
  });
});
