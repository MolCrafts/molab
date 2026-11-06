import { describe, expect, it } from "@rstest/core";
import { isTexDocument } from "./texDocument";

describe("isTexDocument", () => {
  it("matches the manuscript suffixes and nothing else", () => {
    expect(isTexDocument("projects/nve-drift/manuscript/nve-drift.tex")).toBe(true);
    expect(isTexDocument("letter.LTX")).toBe(true);
    expect(isTexDocument("projects/nve-drift/knowledges/nve-drift.md")).toBe(false);
    expect(isTexDocument("figures/tab_drift.tex.bak")).toBe(false);
  });
});
