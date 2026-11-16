import { describe, expect, it } from "@rstest/core";
import type { PanelModel } from "./figure-model";
import {
  axisLabelExpr,
  DEFAULT_STYLE,
  logAxis,
  type MolplotStyle,
  panelNote,
  panelRows,
  panelValue,
  processLine,
  showsRaw,
} from "./panel-data";

const style = (patch: Partial<MolplotStyle> = {}): MolplotStyle => ({ ...DEFAULT_STYLE, ...patch });

const panel = (normalised: boolean, timed = false): PanelModel => ({
  id: "p",
  title: "temperature",
  unit: "K",
  note: null,
  normalised,
  lines: [
    {
      id: "f\u0000temperature",
      label: "temperature",
      color: "var(--c)",
      dash: 5,
      series: {
        id: "f\u0000temperature",
        file: "f",
        key: "temperature",
        unit: "K",
        points: [
          { step: 0, wall: 1000, y: 10 },
          { step: 10, wall: 2000, y: 20 },
          { step: 20, wall: 3000, y: 30 },
        ],
        latest: 30,
        timed,
        replayedFrom: [],
      },
    },
  ],
});

describe("processLine", () => {
  it("returns raw values untouched without smoothing or spike filter", () => {
    expect(processLine([1, 2, 3], false, style({ smoothing: 0 }))).toEqual({
      raw: [1, 2, 3],
      y: [1, 2, 3],
    });
  });

  it("normalises raw to [0, 1] before smoothing", () => {
    const { raw, y } = processLine([10, 20, 30], true, style({ smoothing: 0.5 }));
    expect(raw).toEqual([0, 0.5, 1]);
    expect(y[0]).toBeCloseTo(0);
    expect(y[2]).toBeLessThan(1);
  });

  it("drops a lone spike before the EMA, leaving the raw trace intact", () => {
    const values = Array.from({ length: 30 }, (_, i) => (i === 20 ? 1000 : 1 + (i % 2) * 0.01));
    const { raw, y } = processLine(values, false, style({ smoothing: 0, spikeFilter: true }));
    expect(raw[20]).toBe(1000);
    expect(y[20]).toBeLessThan(2);
  });
});

describe("panelRows", () => {
  it("draws steps on the x axis, with a tooltip naming line, step and value", () => {
    const rows = panelRows(panel(false), style({ smoothing: 0 }));
    expect(rows.map((row) => row.x)).toEqual([0, 10, 20]);
    expect(rows[0].tip).toBe("temperature · step 0 · 10.00");
    expect(rows[0].dash).toBe("1");
  });

  it("drops a line with no wall clock from a Time axis", () => {
    expect(panelRows(panel(false, false), style({ x: "time" }))).toEqual([]);
    expect(panelRows(panel(false, true), style({ x: "time" })).map((row) => row.x)).toEqual([
      1000, 2000, 3000,
    ]);
  });
});

describe("style rules", () => {
  it("shows the raw trace only behind a processed line", () => {
    expect(showsRaw(style({ smoothing: 0.6 }))).toBe(true);
    expect(showsRaw(style({ smoothing: 0 }))).toBe(false);
    expect(showsRaw(style({ smoothing: 0, spikeFilter: true }))).toBe(true);
    expect(showsRaw(style({ raw: false }))).toBe(false);
  });

  it("keeps a normalised panel linear", () => {
    expect(logAxis(style({ y: "log" }), panel(true))).toBe(false);
    expect(logAxis(style({ y: "log" }), panel(false))).toBe(true);
  });

  it("keeps a panel with values at or below zero linear, and says so", () => {
    const negative: PanelModel = {
      ...panel(false),
      lines: panel(false).lines.map((line) => ({
        ...line,
        series: { ...line.series, points: [{ step: 0, wall: 0, y: -1 }] },
      })),
    };
    expect(logAxis(style({ y: "log" }), negative)).toBe(false);
    expect(panelNote(style({ y: "log" }), negative)).toBe("linear: values ≤ 0");
    expect(panelNote(style(), negative)).toBeUndefined();
  });

  it("formats the y axis by notation and digits", () => {
    expect(axisLabelExpr(style({ notation: "auto", digits: 4 }))).toBe(
      "abs(datum.value) >= 1000 ? format(datum.value, '.4~s') : format(datum.value, '.4~g')",
    );
    expect(axisLabelExpr(style({ notation: "scientific", digits: 3 }))).toBe(
      "format(datum.value, '.2e')",
    );
    expect(axisLabelExpr(style({ notation: "decimal", digits: 2 }))).toBe(
      "format(datum.value, '.2~r')",
    );
  });

  it("shows the latest value unless the panel is normalised", () => {
    expect(panelValue(panel(false), style({ notation: "decimal", digits: 3 }))).toBe("30.0");
    expect(panelValue(panel(true), style())).toBeUndefined();
  });
});
