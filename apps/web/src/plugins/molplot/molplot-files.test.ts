/**
 * The view a real run actually gets.
 *
 * Takes the file listing of a finished MD attempt as the API returns it and
 * asks the question the user asks: does the MolPlot view appear, and on which
 * files? It caught the two ways it can silently not — a reader nobody
 * registered, and a product directory nothing was looking in.
 */

import { afterEach, beforeEach, describe, expect, it } from "@rstest/core";
import { applicableRunViews } from "@/app/renderers/run/useRunViews";
import {
  registerMetricReaderContribution,
  unregisterMetricReaderContribution,
} from "@/lib/contribution-runtime";
import { flattenFileNodes } from "@/lib/file-type-discovery";
import { LAMMPS_LOG_READER, MLP_JSONL_READER } from "@/plugins/molrs/plugin";
import { isFigureFile, MOLPLOT_FILES } from "./molplot-files";

/** Exactly what `GET .../executions/e01/files` returns for a peo-tg attempt. */
const RUN_FILES = [
  {
    name: "jobs",
    relPath: "jobs",
    type: "folder",
    children: [
      { name: "lammps-0.sh", relPath: "jobs/lammps-0.sh", type: "file", size: 1106 },
      { name: "lammps-0.out", relPath: "jobs/lammps-0.out", type: "file", size: 1689649 },
    ],
  },
  {
    name: "out",
    relPath: "out",
    type: "folder",
    children: [
      { name: "lammps.log", relPath: "out/lammps.log", type: "file", size: 2990947 },
      { name: "tg.json", relPath: "out/tg.json", type: "file", size: 642484 },
      { name: "tg.mlp.vl.json", relPath: "out/tg.mlp.vl.json", type: "file", size: 2048 },
    ],
  },
  {
    name: "work",
    relPath: "work",
    type: "folder",
    children: [
      { name: "metrics.mlp.jsonl", relPath: "work/metrics.mlp.jsonl", type: "file", size: 241 },
      {
        name: "md",
        relPath: "work/md",
        type: "folder",
        children: [
          { name: "system.data", relPath: "work/md/system.data", type: "file", size: 8656053 },
        ],
      },
    ],
  },
  { name: "execution.json", relPath: "execution.json", type: "file", size: 1132 },
];

const VIEW = {
  id: "molplot",
  label: "MolPlot",
  files: MOLPLOT_FILES,
  Component: () => null,
};

const matched = (): string[] =>
  (applicableRunViews([VIEW], flattenFileNodes(RUN_FILES))[0]?.files ?? [])
    .map((file) => file.relPath)
    .sort();

describe("MolPlot's view on a real attempt", () => {
  beforeEach(() => {
    registerMetricReaderContribution(MLP_JSONL_READER);
    registerMetricReaderContribution(LAMMPS_LOG_READER);
  });

  afterEach(() => {
    unregisterMetricReaderContribution(MLP_JSONL_READER.id);
    unregisterMetricReaderContribution(LAMMPS_LOG_READER.id);
  });

  it("appears, on the solver log, the WAL and the run's own figure", () => {
    expect(matched()).toEqual([
      "jobs/lammps-0.out",
      "out/lammps.log",
      "out/tg.mlp.vl.json",
      "work/metrics.mlp.jsonl",
    ]);
  });

  it("still appears when only the WAL is there — no WASM, no chart lost", () => {
    unregisterMetricReaderContribution(LAMMPS_LOG_READER.id);
    expect(matched()).toEqual(["out/tg.mlp.vl.json", "work/metrics.mlp.jsonl"]);
  });

  it("does not claim files no reader owns", () => {
    const claimed = matched();
    expect(claimed).not.toContain("out/tg.json");
    expect(claimed).not.toContain("work/md/system.data");
    expect(claimed).not.toContain("execution.json");
  });
});

describe("isFigureFile", () => {
  it("is a run's own Vega-Lite figure, and nothing else", () => {
    expect(isFigureFile({ name: "e.mlp.vl.json", relPath: "out/e.mlp.vl.json" })).toBe(true);
    expect(isFigureFile({ name: "e.mlp.index.json", relPath: "e.mlp.index.json" })).toBe(false);
    expect(isFigureFile({ name: "metrics.mlp.jsonl", relPath: "metrics.mlp.jsonl" })).toBe(false);
  });
});
