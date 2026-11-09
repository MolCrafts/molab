import { describe, expect, it } from "@rstest/core";
import type { MetricRecordSample as MetricRecord } from "@/lib/contribution-types";
import {
  coloursBySeries,
  figureSeries,
  fileColors,
  fileLabels,
  groupPanels,
  legendOf,
} from "./figure-model";
import type { SourceRead } from "./read-metrics";
import { PALETTE } from "./scalar-series";

const scalar = (k: string, s: number, v: number, unit?: string): MetricRecord => ({
  t: "scalar",
  k,
  s,
  v,
  ...(unit ? { tags: { unit } } : {}),
});

const source = (path: string, records: MetricRecord[]): SourceRead => ({
  path,
  format: "test",
  label: "test",
  revision: 1,
  tailable: false,
  records,
});

const LOG = source("out/log.lammps", [
  scalar("temperature", 0, 300, "K"),
  scalar("temperature", 1, 301, "K"),
  scalar("pe", 0, -10, "eV"),
  scalar("ke", 0, 4, "eV"),
  scalar("press", 0, 1),
]);
const WAL = source("out/metrics.mlp.jsonl", [
  scalar("temperature", 0, 299, "K"),
  scalar("pe", 0, -11, "eV"),
]);
const SOURCES = [LOG, WAL];
const COLORS = fileColors(SOURCES.map((item) => item.path));

const titles = (groupBy: Parameters<typeof groupPanels>[1]) =>
  groupPanels(figureSeries(SOURCES, null), groupBy, COLORS).map((panel) => panel.title);

describe("figureSeries", () => {
  it("builds one series per key per file, with the declared unit", () => {
    const series = figureSeries(SOURCES, null);
    expect(series).toHaveLength(6);
    expect(series.find((item) => item.key === "press")?.unit).toBeNull();
    expect(series.find((item) => item.key === "pe")?.unit).toBe("eV");
  });
});

describe("fileColors and fileLabels", () => {
  it("gives each file a palette colour in list order", () => {
    expect(COLORS.get("out/log.lammps")).toBe(PALETTE[0]);
    expect(COLORS.get("out/metrics.mlp.jsonl")).toBe(PALETTE[1]);
  });

  it("uses base names unless two collide", () => {
    const labels = fileLabels(["a/log.lammps", "b/log.lammps", "c/metrics.mlp.jsonl"]);
    expect([...labels.values()]).toEqual(["a/log.lammps", "b/log.lammps", "metrics.mlp.jsonl"]);
  });
});

describe("groupPanels", () => {
  it("Quantity: a panel per key, a colour per file", () => {
    expect(titles("quantity")).toEqual(["ke", "pe", "press", "temperature"]);
    const temperature = groupPanels(figureSeries(SOURCES, null), "quantity", COLORS)[3];
    expect(temperature.unit).toBe("K");
    expect(temperature.lines.map((line) => line.color)).toEqual([PALETTE[0], PALETTE[1]]);
    expect(temperature.normalised).toBe(false);
  });

  it("Unit: a panel per unit, quantities told apart by dash; no unit stays alone", () => {
    const panels = groupPanels(figureSeries(SOURCES, null), "unit", COLORS);
    expect(panels.map((panel) => panel.title)).toEqual(["eV", "press", "K"]);
    const energy = panels[0];
    expect(energy.note).toBe("ke · pe");
    expect(energy.lines.map((line) => [line.series.key, line.dash])).toEqual([
      ["ke", 0],
      ["pe", 1],
      ["pe", 1],
    ]);
  });

  it("File: a panel per file, normalised when its units differ", () => {
    const panels = groupPanels(figureSeries(SOURCES, null), "file", COLORS);
    expect(panels.map((panel) => panel.title)).toEqual(["log.lammps", "metrics.mlp.jsonl"]);
    expect(panels.every((panel) => panel.normalised)).toBe(true);
    expect(panels[0].note).toBe("normalised");
  });

  it("None: one normalised panel, a colour per series", () => {
    const [panel, ...rest] = groupPanels(figureSeries(SOURCES, null), "none", COLORS);
    expect(rest).toHaveLength(0);
    expect(panel.normalised).toBe(true);
    expect(new Set(panel.lines.map((line) => line.color)).size).toBe(6);
  });

  it("labels a key with its file only when two files share it", () => {
    const [panel] = groupPanels(figureSeries(SOURCES, null), "none", COLORS);
    const labels = panel.lines.map((line) => line.label);
    expect(labels).toContain("temperature · log.lammps");
    expect(labels).toContain("ke");
  });

  it("is empty when nothing is checked", () => {
    expect(groupPanels([], "none", COLORS)).toEqual([]);
  });
});

describe("legendOf", () => {
  const files = [{ id: "out/log.lammps", label: "log.lammps", color: PALETTE[0] }];

  it("lists files when colours are per file", () => {
    const panels = groupPanels(figureSeries([LOG], null), "quantity", COLORS);
    expect(coloursBySeries("quantity")).toBe(false);
    expect(legendOf("quantity", panels, files)).toEqual(files);
  });

  it("lists every series when colours are per series", () => {
    const panels = groupPanels(figureSeries([LOG], null), "none", COLORS);
    expect(legendOf("none", panels, files).map((entry) => entry.label)).toEqual([
      "ke",
      "pe",
      "press",
      "temperature",
    ]);
  });
});
