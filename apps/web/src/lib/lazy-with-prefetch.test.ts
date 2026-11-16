import { describe, expect, it } from "@rstest/core";
import { lazyWithPrefetch, prefetchLazy } from "./lazy-with-prefetch";

describe("lazyWithPrefetch", () => {
  it("shares one factory promise between prefetch and later prefetch", async () => {
    let calls = 0;
    const Component = lazyWithPrefetch(async () => {
      calls += 1;
      return { default: (() => null) as unknown as import("react").ComponentType<unknown> };
    });

    const first = Component.prefetch();
    const second = Component.prefetch();
    prefetchLazy(Component);
    await first;
    await second;

    expect(calls).toBe(1);
    expect(first).toBe(second);
  });

  it("ignores components without a prefetch hook", () => {
    expect(() => prefetchLazy(undefined)).not.toThrow();
    expect(() => prefetchLazy({})).not.toThrow();
  });
});
