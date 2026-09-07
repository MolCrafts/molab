import { afterEach, beforeEach, describe, expect, it } from "@rstest/core";
import {
  registerMetricReaderContribution,
  unregisterMetricReaderContribution,
} from "@/lib/contribution-runtime";
import { isMetricSurface, knownMetricFormats } from "./metric-formats";

const file = (relPath: string) => ({ name: relPath.split("/").pop() ?? relPath, relPath });

const reader = (id: string, format: string, patterns: string[]) => ({
  id,
  format,
  label: format,
  patterns,
  read: async () => [],
});

describe("molplot's surface gate", () => {
  beforeEach(() => {
    registerMetricReaderContribution(reader("t:wal", "mlp_jsonl", ["**/*.mlp.jsonl"]));
    registerMetricReaderContribution(
      reader("t:lammps", "lammps_log", ["**/log.lammps", "**/lammps*.out"]),
    );
  });

  afterEach(() => {
    unregisterMetricReaderContribution("t:wal");
    unregisterMetricReaderContribution("t:lammps");
    unregisterMetricReaderContribution("t:third-party");
  });

  it("offers a chart for a raw solver log, with nothing converted", () => {
    expect(isMetricSurface(file("out/log.lammps"))).toBe(true);
    expect(isMetricSurface(file("jobs/lammps-0.out"))).toBe(true);
  });

  it("treats molexp's own WAL as one format among others", () => {
    expect(isMetricSurface(file("out/metrics.mlp.jsonl"))).toBe(true);
  });

  it("claims nothing no reader declared", () => {
    expect(isMetricSurface(file("work/build_chain/leap.log"))).toBe(false);
    expect(isMetricSurface(file("run.json"))).toBe(false);
    expect(isMetricSurface(file("out/metrics.mlp.zarr/zarr.json"))).toBe(false);
  });

  it("picks up a format molplot has never heard of, with no change here", () => {
    expect(isMetricSurface(file("out/run.fakesim"))).toBe(false);
    registerMetricReaderContribution(reader("t:third-party", "fake_sim", ["**/*.fakesim"]));
    expect(isMetricSurface(file("out/run.fakesim"))).toBe(true);
    expect(knownMetricFormats().map((entry) => entry.format)).toContain("fake_sim");
  });
});
