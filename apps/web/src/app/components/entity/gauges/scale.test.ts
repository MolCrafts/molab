import { describe, expect, it } from "@rstest/core";

import { formatSpan, spanScale, stackLanes, successShare, timeBuckets } from "./scale";

describe("formatSpan", () => {
  it("reads at a glance at every magnitude", () => {
    expect(formatSpan(2.43)).toBe("2.4s");
    expect(formatSpan(42)).toBe("42s");
    expect(formatSpan(48 * 60)).toBe("48m");
    expect(formatSpan(88 * 60)).toBe("1h 28m");
    expect(formatSpan(2 * 3600)).toBe("2h");
    expect(formatSpan(76 * 3600)).toBe("3d 4h");
    expect(formatSpan(-1)).toBe("—");
  });
});

describe("spanScale", () => {
  it("centres a single value instead of pinning it to an edge", () => {
    const scale = spanScale([2880]);
    expect(scale.log).toBe(false);
    expect(scale.at(2880)).toBeCloseTo(0.5, 5);
  });

  it("goes logarithmic when the spread passes 20x, with ticks inside the domain", () => {
    const scale = spanScale([4, 6 * 3600]);
    expect(scale.log).toBe(true);
    expect(scale.at(4)).toBeLessThan(scale.at(60));
    expect(scale.ticks.length).toBeGreaterThanOrEqual(2);
    expect(scale.ticks.length).toBeLessThanOrEqual(5);
    for (const tick of scale.ticks) {
      expect(scale.at(tick)).toBeGreaterThanOrEqual(0);
      expect(scale.at(tick)).toBeLessThanOrEqual(1);
    }
  });
});

describe("stackLanes", () => {
  it("stacks coincident dots into distinct lanes and leaves distant ones on the axis", () => {
    const lanes = stackLanes([0.5, 0.5, 0.5, 0.9]);
    expect(new Set(lanes.slice(0, 3)).size).toBe(3);
    expect(lanes[3]).toBe(0);
  });
});

describe("successShare", () => {
  it("is null until something finished, and ignores live work", () => {
    const base = { total: 3, running: 3, pending: 0, succeeded: 0, failed: 0, cancelled: 0 };
    expect(successShare(base)).toBeNull();
    expect(successShare({ ...base, total: 6, succeeded: 1, failed: 2 })).toBeCloseTo(1 / 3);
  });
});

describe("timeBuckets", () => {
  it("counts starts and finishes by outcome, dropping events outside the window", () => {
    const now = 10_000;
    const buckets = timeBuckets(
      [
        { startedAt: 9_100, finishedAt: 9_900, outcome: "failed" },
        { startedAt: 500, finishedAt: 9_950, outcome: "succeeded" },
        { startedAt: 9_990, finishedAt: null, outcome: "running" },
      ],
      now,
      1_000,
      2,
    );
    expect(buckets.map((bucket) => bucket.starts)).toEqual([1, 1]);
    expect(buckets[1]?.finishes).toEqual({ succeeded: 1, failed: 1, cancelled: 0, other: 0 });
  });
});
