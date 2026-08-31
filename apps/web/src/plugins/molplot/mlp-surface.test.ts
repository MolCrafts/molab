import { describe, expect, it } from "@rstest/core";

import { isMlpMetricsSurface } from "./mlp-surface";

const file = (relPath: string) => ({
  name: relPath.split("/").pop() ?? relPath,
  relPath,
});

describe("isMlpMetricsSurface", () => {
  it("matches JSONL WAL including under artifacts/", () => {
    expect(isMlpMetricsSurface(file("metrics.mlp.jsonl"))).toBe(true);
    expect(isMlpMetricsSurface(file("artifacts/run.mlp.jsonl"))).toBe(true);
  });

  it("does not match leftover zarr stores", () => {
    expect(isMlpMetricsSurface(file("metrics.mlp.zarr"))).toBe(false);
    expect(isMlpMetricsSurface(file("metrics.mlp.zarr/zarr.json"))).toBe(false);
    expect(isMlpMetricsSurface(file("metrics.mlp.zarr/series/zarr.json"))).toBe(false);
  });

  it("does not match the host index cache", () => {
    expect(isMlpMetricsSurface(file("metrics.mlp.index.json"))).toBe(false);
  });
});
