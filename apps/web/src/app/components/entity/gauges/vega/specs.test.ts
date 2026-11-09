import { compileVegaLite } from "@molcrafts/ui-vega-lite";
import { describe, expect, it } from "@rstest/core";

import {
  activitySpec,
  barsSpec,
  compareBarsSpec,
  durationSpec,
  mixSpec,
  sweepSpec,
  taskClockSpec,
} from "./chartSpecs";
import { brushedWindow, clickedKey, type OverviewPalette } from "./common";
import { DIAL, dialRows, dialSpec, rangeSpec, unitSpec } from "./instrumentSpecs";

const palette: OverviewPalette = {
  status: {
    running: "rgb(0, 0, 255)",
    queued: "rgb(100, 100, 140)",
    interrupted: "rgb(200, 150, 0)",
    succeeded: "rgb(0, 160, 0)",
    failed: "rgb(220, 0, 0)",
    cancelled: "rgb(120, 120, 120)",
  },
  accent: "rgb(0, 95, 184)",
  ink: "rgb(36, 36, 36)",
  muted: "rgb(97, 97, 97)",
  rule: "rgb(229, 229, 229)",
  ground: "rgb(255, 255, 255)",
  font: "Geist, sans-serif",
};

const axis = { domain: [600, 7200] as [number, number], ticks: [900, 1800, 3600], log: false };
const window = { from: Date.parse("2026-11-01T00:00:00Z"), to: Date.parse("2026-11-02T00:00:00Z") };

const signalNames = async (spec: ReturnType<typeof dialSpec>): Promise<string[]> =>
  ((await compileVegaLite(spec)).signals ?? []).map((signal) => signal.name);

describe("overview chart specs", () => {
  it.each([
    ["dial", dialSpec(palette)],
    ["unit meter", unitSpec(palette, 0.5)],
    ["unit meter without reference", unitSpec(palette, null)],
    ["duration range", rangeSpec(palette, axis)],
    ["activity", activitySpec(palette, window)],
    ["status mix", mixSpec(palette, 3)],
    ["durations", durationSpec(palette, { ...axis, log: true }, ["NVE Drift", "Protein Folding"])],
    ["tasks on a clock", taskClockSpec(palette, 3, window)],
    [
      "compare bars",
      compareBarsSpec(palette, 3, { domain: [1e-5, 1e-3], log: true, baseline: 3e-5 }),
    ],
    [
      "sweep",
      sweepSpec(palette, {
        labels: ["0.5 fs", "1 fs"],
        log: true,
        domain: [1e-5, 1e-3],
        small: true,
      }),
    ],
  ])("%s compiles to Vega", async (_name, spec) => {
    await expect(compileVegaLite(spec)).resolves.toBeTruthy();
  });

  it("exposes the shared interaction signals", async () => {
    expect(await signalNames(dialSpec(palette))).toEqual(expect.arrayContaining(["hover"]));
    expect(await signalNames(mixSpec(palette, 2))).toEqual(expect.arrayContaining(["hover"]));
    expect(await signalNames(activitySpec(palette, window))).toEqual(
      expect.arrayContaining(["hover", "brush"]),
    );
  });
});

describe("dialRows", () => {
  const shares = [
    { key: "succeeded", count: 3, color: "green", tip: "" },
    { key: "failed", count: 1, color: "red", tip: "" },
    { key: "cancelled", count: 0, color: "grey", tip: "" },
  ];

  it("starts the completed segment at the dial's zero and skips empty shares", () => {
    const segments = dialRows(shares).filter((row) => row.layer === "segment");
    expect(segments.map((row) => row.key)).toEqual(["succeeded", "failed"]);
    const sweep = (4 * Math.PI) / 3;
    expect(segments[0]?.theta).toBeCloseTo(-sweep / 2, 6);
    expect(segments[1]?.theta2).toBeCloseTo(sweep / 2, 6);
    // 3 of 4 over the sweep left after one gap.
    expect(segments[0]?.theta2).toBeCloseTo(-sweep / 2 + 0.75 * (sweep - 0.035), 6);
  });

  it("draws only the track and ticks before anything finishes", () => {
    const rows = dialRows([{ key: "succeeded", count: 0, color: "g", tip: "" }]);
    expect(rows.some((row) => row.layer === "segment")).toBe(false);
    expect(rows.filter((row) => row.layer === "tick")).toHaveLength(5);
    expect(rows[0]?.r1).toBe(DIAL.outer);
  });
});

describe("selection values", () => {
  it("reads the clicked row's key and ignores chrome", () => {
    expect(clickedKey({ datum: { key: "run-1" } })).toBe("run-1");
    expect(clickedKey({ datum: {} })).toBeNull();
    expect(clickedKey(null)).toBeNull();
  });

  it("orders a brushed window and drops an empty one", () => {
    expect(brushedWindow({ start: [2000, 1000] }, "start")).toEqual([1000, 2000]);
    expect(brushedWindow({ start: [new Date(5), new Date(9)] }, "start")).toEqual([5, 9]);
    expect(brushedWindow({ start: [7, 7] }, "start")).toBeNull();
    expect(brushedWindow({}, "start")).toBeNull();
  });
});

describe("count bars", () => {
  it.each([
    ["vertical", barsSpec(palette, "vertical", 4, "format(datum.value, 'd')")],
    ["horizontal", barsSpec(palette, "horizontal", 3, "format(datum.value, 'd')")],
  ])("%s bars compile", async (_name, spec) => {
    await expect(compileVegaLite(spec)).resolves.toBeTruthy();
  });
});
