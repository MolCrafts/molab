import { compileVegaLite } from "@molcrafts/ui-vega-lite";
import { describe, expect, it } from "@rstest/core";
import type { OverviewPalette } from "@/app/components/entity/gauges/vega/common";
import { figureSpec, figureTitle, parseFigure, seriesSpec } from "./panel-spec";

const palette = {
  status: {},
  accent: "var(--a)",
  ink: "var(--i)",
  muted: "var(--m)",
  rule: "var(--r)",
  ground: "var(--g)",
  font: "Geist, sans-serif",
} as unknown as OverviewPalette;

const options = {
  height: 140,
  time: false,
  log: false,
  yLabels: "format(datum.value, '~g')",
  raw: true,
};

const layers = (spec: object): { mark: { type: string; opacity?: number } }[] =>
  (spec as { layer: { mark: { type: string; opacity?: number } }[] }).layer;

describe("seriesSpec", () => {
  it("compiles, drawing the raw trace at 25% under the smoothed line", async () => {
    const spec = seriesSpec(palette, options);
    await expect(compileVegaLite(spec)).resolves.toBeDefined();
    const [raw, smoothed] = layers(spec);
    expect(raw.mark.opacity).toBe(0.25);
    expect(smoothed.mark.type).toBe("line");
  });

  it("omits the raw layer when raw is hidden, and compiles on a log time axis", async () => {
    const spec = seriesSpec(palette, { ...options, raw: false, log: true, time: true });
    expect(layers(spec)).toHaveLength(2);
    await expect(compileVegaLite(spec)).resolves.toBeDefined();
  });

  it("draws in the app's type, never Vega's serif default", () => {
    const spec = seriesSpec(palette, options) as { config: { font: string } };
    expect(spec.config.font).toBe("Geist, sans-serif");
  });
});

describe("figures", () => {
  const authored = parseFigure(
    JSON.stringify({
      title: "Potential energy convergence",
      width: 600,
      data: { values: [{ step: 0, energy: 1 }] },
      mark: "line",
      encoding: {
        x: { field: "step", type: "quantitative" },
        y: { field: "energy", type: "quantitative" },
      },
    }),
  );

  it("drops the authored title and size, paints in the file colour, and compiles", async () => {
    const spec = figureSpec(palette, authored, "var(--file)", 140) as unknown as Record<
      string,
      unknown
    >;
    expect(spec.title).toBeUndefined();
    expect(spec.width).toBeUndefined();
    expect(spec.height).toBe(140);
    expect((spec.config as { line: { color: string } }).line.color).toBe("var(--file)");
    await expect(compileVegaLite(spec as never)).resolves.toBeDefined();
  });

  it("reads the title for the panel", () => {
    expect(figureTitle(authored)).toBe("Potential energy convergence");
    expect(figureTitle({ title: { text: "T" } })).toBe("T");
    expect(figureTitle({})).toBeNull();
  });

  it("refuses a file that is not a Vega-Lite object", () => {
    expect(() => parseFigure("[1, 2]")).toThrow("not a Vega-Lite object");
  });
});
