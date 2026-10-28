import { describe, expect, it } from "@rstest/core";

import { directoryLoader } from "./loadMolvisCore";

describe("directoryLoader", () => {
  it("uses loadMrecSource when the stage exports it", () => {
    const current = async () => {};
    const previous = async () => {};
    expect(directoryLoader({ loadMrecSource: current, loadZarrSource: previous })).toBe(current);
  });

  it("falls back to the previous export name", () => {
    const previous = async () => {};
    expect(directoryLoader({ loadZarrSource: previous })).toBe(previous);
  });
});
