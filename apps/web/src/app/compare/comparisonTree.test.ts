/**
 * Pure-logic tests for the comparison's project → experiment → run grouping. Node
 * environment: no React, no DOM.
 */

import { describe, expect, it } from "@rstest/core";

import {
  buildComparisonTree,
  type ComparisonRunNode,
  comparisonSpansWorkspaces,
  groupCheckState,
  runsOfProject,
} from "./comparisonTree";
import type { CompareEntry, RunRef } from "./types";

const ref = (
  workspaceKey: string,
  projectId: string,
  experimentId: string,
  runId: string,
): RunRef => ({ workspaceKey, projectId, experimentId, runId });

const entry = (
  r: RunRef,
  names: { ws?: string; project?: string; experiment?: string; run?: string } = {},
  selected = true,
): CompareEntry => ({
  ref: r,
  selected,
  executionId: null,
  workspaceLabel: names.ws ?? r.workspaceKey,
  projectName: names.project ?? r.projectId,
  experimentName: names.experiment ?? r.experimentId,
  runName: names.run ?? r.runId,
  parameters: {},
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

    // Second-staged project stays second, and a project already present is not
    // pulled to the end when another of its runs arrives.
    expect(tree.map((p) => p.name)).toEqual(["zeta", "alpha"]);
    expect(tree[0].experiments.map((e) => e.name)).toEqual(["e1", "e3"]);
  });

  it("separates same-named projects served from different workspaces", () => {
    // Display names collide constantly across machines; the ref is what
    // decides, so these must not merge into one node.
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

  it("addresses each run by its refKey", () => {
    const tree = buildComparisonTree([entry(ref("lab", "p", "e", "r"))]);
    expect(tree[0].experiments[0].runs[0].key).toBe("lab/p/e/r");
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

describe("groupCheckState", () => {
  const node = (selected: boolean): ComparisonRunNode => ({
    key: `k${selected}`,
    entry: entry(ref("w", "p", "e", `r${selected}`), {}, selected),
  });

  it("reads checked, unchecked and indeterminate off its runs", () => {
    expect(groupCheckState([node(true), node(true)])).toBe("checked");
    expect(groupCheckState([node(false), node(false)])).toBe("unchecked");
    expect(groupCheckState([node(true), node(false)])).toBe("indeterminate");
  });

  it("treats an empty group as unticked rather than fully ticked", () => {
    expect(groupCheckState([])).toBe("unchecked");
  });
});

describe("runsOfProject", () => {
  it("flattens every experiment's runs in order", () => {
    const [project] = buildComparisonTree([
      entry(ref("lab", "p", "e1", "r1")),
      entry(ref("lab", "p", "e2", "r2")),
      entry(ref("lab", "p", "e1", "r3")),
    ]);
    expect(runsOfProject(project).map((r) => r.entry.runName)).toEqual(["r1", "r3", "r2"]);
  });
});
