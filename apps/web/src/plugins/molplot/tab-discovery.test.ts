/**
 * The tab a real run actually gets.
 *
 * The unit tests above check patterns against hand-written names. This one
 * takes the file listing of a finished MD attempt as the API returns it and
 * asks the question the user asks: does the MolPlot tab appear? It caught the
 * two ways it can silently not — a reader nobody registered, and a product
 * directory nothing was looking in.
 */

import { afterEach, beforeEach, describe, expect, it } from "@rstest/core";
import {
  registerMetricReaderContribution,
  unregisterMetricReaderContribution,
} from "@/lib/contribution-runtime";
import type { FileTypeContribution } from "@/lib/contribution-types";
import { discoverPlugins, flattenFileNodes } from "@/lib/file-type-discovery";
import { LAMMPS_LOG_READER, MLP_JSONL_READER } from "@/plugins/molrs/plugin";
import { isMetricSurface } from "./metric-formats";

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

/** molplot's own registration, minus the React component. */
const molplotTab: FileTypeContribution = {
  id: "molplot:run-tab",
  objectType: "run",
  value: "molplot",
  label: "MolPlot",
  priority: 40,
  matcher: {
    patterns: ["**/*.mlp.vl.json", "*.mlp.vl.json"],
    matches: (file) => isMetricSurface(file),
  },
  Component: (() => null) as unknown as FileTypeContribution["Component"],
};

describe("MolPlot's tab on a real attempt", () => {
  beforeEach(() => {
    registerMetricReaderContribution(MLP_JSONL_READER);
    registerMetricReaderContribution(LAMMPS_LOG_READER);
  });

  afterEach(() => {
    unregisterMetricReaderContribution(MLP_JSONL_READER.id);
    unregisterMetricReaderContribution(LAMMPS_LOG_READER.id);
  });

  it("appears, and claims the solver log the run actually wrote", () => {
    const [discovered] = discoverPlugins([molplotTab], flattenFileNodes(RUN_FILES));
    expect(discovered).toBeDefined();
    expect(discovered.files.map((file) => file.relPath).sort()).toEqual([
      "jobs/lammps-0.out",
      "out/lammps.log",
      "work/metrics.mlp.jsonl",
    ]);
  });

  it("still appears when only the WAL is there — no WASM, no chart lost", () => {
    // The LAMMPS reader registers after a capability probe resolves. Until it
    // does, molplot must already be reachable through the formats that need
    // no binding, or the tab flickers into existence mid-session.
    unregisterMetricReaderContribution(LAMMPS_LOG_READER.id);
    const [discovered] = discoverPlugins([molplotTab], flattenFileNodes(RUN_FILES));
    expect(discovered?.files.map((file) => file.relPath)).toEqual(["work/metrics.mlp.jsonl"]);
  });

  it("does not claim files no reader owns", () => {
    const [discovered] = discoverPlugins([molplotTab], flattenFileNodes(RUN_FILES));
    const claimed = discovered.files.map((file) => file.relPath);
    expect(claimed).not.toContain("out/tg.json");
    expect(claimed).not.toContain("work/md/system.data");
    expect(claimed).not.toContain("execution.json");
  });
});
