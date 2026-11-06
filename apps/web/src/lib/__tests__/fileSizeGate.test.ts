import { describe, expect, it } from "@rstest/core";
import {
  canAutoLoad,
  FULL_LOAD_MAX_BYTES,
  fileSizeGate,
  WINDOW_BYTES,
  windowForDecision,
} from "@/lib/fileSizeGate";

describe("fileSizeGate", () => {
  it("loads a small file in full", () => {
    expect(fileSizeGate(1024)).toEqual({ kind: "full" });
  });

  it("loads a file exactly at the threshold in full", () => {
    // Boundary is inclusive — a file of exactly the cap is still one request.
    expect(fileSizeGate(FULL_LOAD_MAX_BYTES).kind).toBe("full");
  });

  it("flags a file one byte over the threshold as oversized", () => {
    expect(fileSizeGate(FULL_LOAD_MAX_BYTES + 1).kind).toBe("oversized");
  });

  it("reports a human size and a bounded window for an oversized file", () => {
    const decision = fileSizeGate(5 * 1024 * 1024 * 1024);

    expect(decision).toEqual({
      kind: "oversized",
      sizeBytes: 5 * 1024 * 1024 * 1024,
      sizeLabel: "5.0 GB",
      windowBytes: WINDOW_BYTES,
    });
  });

  it("keeps the offered window smaller than the full-load cap", () => {
    // Otherwise "load anyway" would be a bigger request than the one refused.
    expect(WINDOW_BYTES).toBeLessThan(FULL_LOAD_MAX_BYTES);
  });

  it("treats an empty file as loadable", () => {
    expect(fileSizeGate(0).kind).toBe("full");
  });

  it("falls back to unknown when the tree carries no size", () => {
    expect(fileSizeGate(null).kind).toBe("unknown");
    expect(fileSizeGate(undefined).kind).toBe("unknown");
  });

  it("treats a non-finite or negative size as unknown rather than oversized", () => {
    // A bad value must not silently block the viewer; the server still caps.
    expect(fileSizeGate(Number.NaN).kind).toBe("unknown");
    expect(fileSizeGate(Number.POSITIVE_INFINITY).kind).toBe("unknown");
    expect(fileSizeGate(-1).kind).toBe("unknown");
  });
});

describe("canAutoLoad", () => {
  it("permits small and unknown sizes, refuses oversized", () => {
    expect(canAutoLoad(10)).toBe(true);
    expect(canAutoLoad(null)).toBe(true);
    expect(canAutoLoad(FULL_LOAD_MAX_BYTES + 1)).toBe(false);
  });
});

describe("windowForDecision", () => {
  it("returns no window for a file that loads in full", () => {
    expect(windowForDecision(fileSizeGate(10))).toBeUndefined();
  });

  it("returns no window when the size is unknown", () => {
    expect(windowForDecision(fileSizeGate(null))).toBeUndefined();
  });

  it("defaults an oversized file to a head window", () => {
    expect(windowForDecision(fileSizeGate(FULL_LOAD_MAX_BYTES + 1))).toEqual({
      mode: "head",
      maxBytes: WINDOW_BYTES,
    });
  });

  it("honours a tail request, which is what logs need", () => {
    expect(windowForDecision(fileSizeGate(FULL_LOAD_MAX_BYTES + 1), "tail")).toEqual({
      mode: "tail",
      maxBytes: WINDOW_BYTES,
    });
  });
});
