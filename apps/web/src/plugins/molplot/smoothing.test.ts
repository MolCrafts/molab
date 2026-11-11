import { describe, expect, it } from "@rstest/core";

import { filterSpikes, smoothEma } from "./smoothing";

describe("smoothEma", () => {
  it("returns a copy unchanged when weight is 0", () => {
    const ys = [1, 2, 3];
    expect(smoothEma(ys, 0)).toEqual(ys);
    expect(smoothEma(ys, 0)).not.toBe(ys);
  });

  it("pulls a lone spike toward the surrounding values", () => {
    const ys = [1, 1, 1, 100, 1, 1, 1];
    const smoothed = smoothEma(ys, 0.6);
    expect(smoothed[3]).toBeGreaterThan(1);
    expect(smoothed[3]).toBeLessThan(100);
  });
});

describe("filterSpikes", () => {
  it("replaces a lone spike with the look-behind median", () => {
    const ys = Array.from({ length: 24 }, () => 1);
    ys[20] = 1000;
    const filtered = filterSpikes(ys);
    expect(filtered[20]).toBe(1);
    expect(filtered.filter((_, i) => i !== 20)).toEqual(ys.filter((_, i) => i !== 20));
  });

  it("does not rewrite earlier points when a later spike arrives (causal)", () => {
    const ys = Array.from({ length: 24 }, () => 1);
    ys[20] = 1000;
    const filtered = filterSpikes(ys);
    expect(filtered.slice(0, 20)).toEqual(ys.slice(0, 20));
  });

  it("leaves a linear ramp intact", () => {
    const ys = Array.from({ length: 30 }, (_, i) => i * 0.1);
    expect(filterSpikes(ys)).toEqual(ys);
  });

  it("passes empty, short, and NaN inputs through without throwing", () => {
    expect(filterSpikes([])).toEqual([]);
    expect(filterSpikes([1, 2, 3])).toEqual([1, 2, 3]);
    const withNan = [1, 1, 1, 1, 1, Number.NaN, 1];
    const out = filterSpikes(withNan);
    expect(Number.isNaN(out[5])).toBe(true);
    expect(out[6]).toBe(1);
  });
});
