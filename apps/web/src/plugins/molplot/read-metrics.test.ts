import { afterEach, beforeEach, describe, expect, it } from "@rstest/core";
import {
  registerMetricReaderContribution,
  unregisterMetricReaderContribution,
} from "@/lib/contribution-runtime";
import { claimableFiles } from "./read-metrics";

/**
 * The browser-side read path.
 *
 * What matters here is the division of labour: the server lists files and
 * hands back bytes, and every decision about what is plottable is made on
 * this side by a contributed reader. So these tests register readers and
 * check what gets *claimed* — never what a server said.
 */

const reader = (id: string, format: string, patterns: string[]) => ({
  id,
  format,
  label: format,
  patterns,
  read: async () => [],
});

const file = (relPath: string, size = 10) => ({
  name: relPath.split("/").pop() ?? relPath,
  relPath,
  type: "file",
  size,
});

describe("claimableFiles", () => {
  beforeEach(() => {
    registerMetricReaderContribution(reader("t:wal", "mlp_jsonl", ["**/*.mlp.jsonl"]));
    registerMetricReaderContribution(
      reader("t:lammps", "lammps_log", ["**/log.lammps", "**/lammps*.out"]),
    );
  });

  afterEach(() => {
    unregisterMetricReaderContribution("t:wal");
    unregisterMetricReaderContribution("t:lammps");
  });

  it("claims a raw solver log, with nothing converted first", () => {
    const claimed = claimableFiles([file("out/log.lammps")]);
    expect(claimed.map((item) => item.reader.format)).toEqual(["lammps_log"]);
  });

  it("descends the nested tree the file API returns", () => {
    const claimed = claimableFiles([
      {
        name: "out",
        relPath: "out",
        type: "dir",
        children: [file("out/log.lammps"), file("out/metrics.mlp.jsonl")],
      },
    ]);
    expect(claimed.map((item) => item.path).sort()).toEqual([
      "out/log.lammps",
      "out/metrics.mlp.jsonl",
    ]);
  });

  it("leaves alone every file no reader declared", () => {
    const claimed = claimableFiles([
      file("run.json"),
      file("work/build_chain/leap.log"),
      file("out/cooled.data"),
    ]);
    expect(claimed).toEqual([]);
  });

  it("carries the size through, so a tailable source can tell it grew", () => {
    const claimed = claimableFiles([file("out/metrics.mlp.jsonl", 4096)]);
    expect(claimed[0].size).toBe(4096);
  });

  it("picks up a format nothing here knows, once its reader is contributed", () => {
    expect(claimableFiles([file("out/run.fakesim")])).toEqual([]);
    registerMetricReaderContribution(reader("t:third", "fake_sim", ["**/*.fakesim"]));
    try {
      expect(claimableFiles([file("out/run.fakesim")])[0].reader.format).toBe("fake_sim");
    } finally {
      unregisterMetricReaderContribution("t:third");
    }
  });
});

describe("tier ordering", () => {
  const dirs = [
    { name: "artifacts", purpose: "Promoted.", versioned: true, products: true },
    { name: "out", purpose: "Bulk.", versioned: false, products: true },
    { name: "work", purpose: "Scratch.", versioned: false, products: false },
  ];
  const node = (relPath: string) => ({
    name: relPath.split("/").pop() ?? relPath,
    relPath,
    type: "file",
    size: 1,
  });

  beforeEach(() => {
    registerMetricReaderContribution({
      id: "t:tier",
      format: "mlp_jsonl",
      label: "WAL",
      patterns: ["**/*.mlp.jsonl"],
      read: async () => [],
    });
  });

  afterEach(() => {
    unregisterMetricReaderContribution("t:tier");
  });

  it("puts the promoted copy ahead of the raw one it came from", () => {
    // The same WAL exists in two tiers after a promotion. The registered one
    // is the answer; which that is comes from the server, not from the name.
    const claimed = claimableFiles(
      [node("out/metrics.mlp.jsonl"), node("artifacts/metrics.mlp.jsonl")],
      dirs,
    );
    expect(claimed.map((c) => c.path)).toEqual([
      "artifacts/metrics.mlp.jsonl",
      "out/metrics.mlp.jsonl",
    ]);
  });

  it("keeps a scratch file last instead of dropping it", () => {
    // A run whose only metrics landed in scratch should still chart.
    const claimed = claimableFiles(
      [node("work/metrics.mlp.jsonl"), node("artifacts/metrics.mlp.jsonl")],
      dirs,
    );
    expect(claimed.map((c) => c.path)).toEqual([
      "artifacts/metrics.mlp.jsonl",
      "work/metrics.mlp.jsonl",
    ]);
  });

  it("is a no-op when the server sent no declarations", () => {
    const paths = [node("work/a.mlp.jsonl"), node("artifacts/b.mlp.jsonl")];
    expect(claimableFiles(paths).map((c) => c.path)).toEqual([
      "work/a.mlp.jsonl",
      "artifacts/b.mlp.jsonl",
    ]);
  });
});
