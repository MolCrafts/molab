import { describe, expect, it } from "@rstest/core";

import { legendEntries } from "./ChartLegend";

const PALETTE = ["#a", "#b", "#c"];

describe("legendEntries", () => {
  it("keeps one entry per label, in series order", () => {
    const entries = legendEntries(
      [
        { id: "r1", label: "n=8", color: "#111" },
        { id: "r2", label: "n=16", color: "#222" },
      ],
      PALETTE,
    );
    expect(entries.map((e) => e.label)).toEqual(["n=8", "n=16"]);
    expect(entries.map((e) => e.color)).toEqual(["#111", "#222"]);
  });

  it("folds series that share a label into one row and counts them", () => {
    // Colour follows the group: every seed of one experiment is one colour,
    // so five rows saying the same thing would be five times nothing.
    const entries = legendEntries(
      [
        { id: "s0", label: "nve", color: "#111" },
        { id: "s1", label: "nve", color: "#111" },
        { id: "s2", label: "npt", color: "#222" },
      ],
      PALETTE,
    );
    expect(entries).toEqual([
      { label: "nve", color: "#111", count: 2 },
      { label: "npt", color: "#222", count: 1 },
    ]);
  });

  it("falls back to the id when a series carries no label", () => {
    expect(legendEntries([{ id: "energy" }], PALETTE)[0].label).toBe("energy");
  });

  it("cycles the palette by entry, matching how the chart assigns colour", () => {
    const entries = legendEntries([{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }], PALETTE);
    expect(entries.map((e) => e.color)).toEqual(["#a", "#b", "#c", "#a"]);
  });

  it("is empty for no series", () => {
    expect(legendEntries([], PALETTE)).toEqual([]);
  });
});
