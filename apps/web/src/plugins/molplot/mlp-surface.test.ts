import { describe, expect, it } from "@rstest/core";

import { isMlpMetricsSurface } from "./mlp-surface";

const file = (relPath: string) => ({
  name: relPath.split("/").pop() ?? relPath,
  relPath,
});

describe("isMlpMetricsSurface", () => {
  it("matches the WAL and the store-root zarr.json", () => {
    expect(isMlpMetricsSurface(file("metrics.mlp.jsonl"))).toBe(true);
    expect(isMlpMetricsSurface(file("artifacts/run.mlp.jsonl"))).toBe(true);
    expect(isMlpMetricsSurface(file("metrics.mlp.zarr"))).toBe(true);
    expect(isMlpMetricsSurface(file("metrics.mlp.zarr/zarr.json"))).toBe(true);
  });

  it("does not match nested zarr arrays or chunks", () => {
    expect(isMlpMetricsSurface(file("metrics.mlp.zarr/series/zarr.json"))).toBe(false);
    expect(isMlpMetricsSurface(file("metrics.mlp.zarr/series/n_frames/zarr.json"))).toBe(false);
    expect(isMlpMetricsSurface(file("metrics.mlp.zarr/series/n_frames/c"))).toBe(false);
    expect(isMlpMetricsSurface(file("metrics.mlp.zarr/series/n_frames__wall/zarr.json"))).toBe(
      false,
    );
  });

  it("does not match the host index cache", () => {
    expect(isMlpMetricsSurface(file("metrics.mlp.index.json"))).toBe(false);
  });
});
