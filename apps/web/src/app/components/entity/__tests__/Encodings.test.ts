import { describe, expect, it } from "@rstest/core";

import { histogramBuckets } from "../Encodings";

describe("histogramBuckets", () => {
  it("returns nothing for an empty sample", () => {
    expect(histogramBuckets([], 8)).toEqual([]);
  });

  it("clamps the bucket count to the sample size", () => {
    expect(histogramBuckets([1, 2], 12)).toHaveLength(2);
  });

  it("puts the sample maximum in the last bucket rather than past the end", () => {
    const buckets = histogramBuckets([0, 5, 10], 3);
    expect(buckets.map((bucket) => bucket.count)).toEqual([1, 1, 1]);
    expect(buckets[2]?.to).toBe(10);
  });

  it("collapses a zero-width range onto one bucket", () => {
    const buckets = histogramBuckets([7, 7, 7], 4);
    expect(buckets).toHaveLength(1);
    expect(buckets[0]).toMatchObject({ from: 7, to: 7, count: 3 });
  });

  it("separates a bimodal sample instead of averaging it away", () => {
    const buckets = histogramBuckets([1, 1, 1, 100, 100], 10);
    expect(buckets[0]?.count).toBe(3);
    expect(buckets[buckets.length - 1]?.count).toBe(2);
    expect(buckets.slice(1, -1).every((bucket) => bucket.count === 0)).toBe(true);
  });

  it("is insensitive to input order", () => {
    const ordered = histogramBuckets([1, 2, 3, 4], 4);
    const shuffled = histogramBuckets([4, 1, 3, 2], 4);
    expect(shuffled).toEqual(ordered);
  });
});
