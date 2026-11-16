/**
 * Colour grouping: which runs share a colour, and how the choice round-trips
 * through the select control.
 */

import { describe, expect, it } from "@rstest/core";

import { colorByFromValue, colorByToValue, groupableParameters, groupLabels } from "./grouping";
import { type CompareEntry, type RunRef, refKey } from "./types";

const entry = (
  ws: string,
  project: string,
  experiment: string,
  run: string,
  parameters: Record<string, unknown> = {},
): CompareEntry => {
  const ref: RunRef = {
    workspaceKey: ws,
    projectId: project,
    experimentId: experiment,
    runId: run,
  };
  return {
    ref,
    executionId: null,
    workspaceLabel: ws,
    projectName: project,
    experimentName: experiment,
    runName: run,
    parameters,
    addedAt: "2026-09-06T00:00:00.000Z",
  };
};

const labelsOf = (
  entries: CompareEntry[],
  colorBy: Parameters<typeof groupLabels>[1],
): string[] => {
  const map = groupLabels(entries, colorBy);
  return entries.map((e) => map.get(refKey(e.ref)) ?? "");
};

describe("groupLabels", () => {
  const entries = [
    entry("lab-v3", "peo", "n-series", "n=8", { seed: 1, n: 8 }),
    entry("lab-v3", "peo", "n-series", "n=12", { seed: 1, n: 12 }),
    entry("pot-precision", "mace", "s3", "fp32-s0", { seed: 2 }),
  ];

  it("labels every run individually under 'run', reusing the tray's shortening", () => {
    expect(labelsOf(entries, { kind: "run" })).toEqual(["n=8", "n=12", "fp32-s0"]);
  });

  it("collapses runs of one experiment onto a shared label", () => {
    expect(labelsOf(entries, { kind: "experiment" })).toEqual(["n-series", "n-series", "s3"]);
  });

  it("groups by workspace and by project", () => {
    expect(labelsOf(entries, { kind: "workspace" })).toEqual(["lab-v3", "lab-v3", "pot-precision"]);
    expect(labelsOf(entries, { kind: "project" })).toEqual(["peo", "peo", "mace"]);
  });

  it("names the parameter as well as its value, so the legend is readable", () => {
    expect(labelsOf(entries, { kind: "parameter", name: "seed" })).toEqual([
      "seed=1",
      "seed=1",
      "seed=2",
    ]);
  });

  it("keeps a run missing the parameter in its own group rather than folding it in", () => {
    expect(labelsOf(entries, { kind: "parameter", name: "n" })).toEqual(["n=8", "n=12", "n unset"]);
  });
});

describe("groupableParameters", () => {
  it("returns the sorted union across the set", () => {
    expect(
      groupableParameters([
        entry("w", "p", "e", "a", { seed: 1, hidden: 64 }),
        entry("w", "p", "e", "b", { seed: 2, lr: 0.1 }),
      ]),
    ).toEqual(["hidden", "lr", "seed"]);
  });
});

describe("colorBy serialisation", () => {
  it("round-trips every kind", () => {
    for (const value of ["run", "experiment", "project", "workspace", "param:seed"]) {
      expect(colorByToValue(colorByFromValue(value))).toBe(value);
    }
  });

  it("falls back to run for an unknown value", () => {
    expect(colorByFromValue("nonsense")).toEqual({ kind: "run" });
  });

  it("handles a parameter whose name contains a colon", () => {
    const parsed = colorByFromValue("param:a:b");
    expect(parsed).toEqual({ kind: "parameter", name: "a:b" });
    expect(colorByToValue(parsed)).toBe("param:a:b");
  });
});
