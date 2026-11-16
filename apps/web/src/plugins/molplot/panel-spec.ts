/**
 * Vega-Lite specs for MolPlot's panels, in the app's type and palette (the
 * overview charts' `baseConfig`): a series panel (smoothed line over the raw
 * one at 25%), and a run's own Vega-Lite figure (`*.mlp.vl.json`) restyled to
 * match. Line colours arrive resolved on each row. Pure: no React, no DOM.
 */

import type { VegaLiteSpec } from "@molcrafts/ui-vega-lite";
import {
  asSpec,
  baseConfig,
  type OverviewPalette,
} from "@/app/components/entity/gauges/vega/common";
import { DASH_PATTERNS } from "./panel-data";

/** Chart height of a panel in the grid, and of a panel alone or enlarged. */
export const PANEL_HEIGHT = 140;
export const PANEL_HEIGHT_WIDE = 320;

/** The raw trace behind a smoothed line. */
const RAW_OPACITY = 0.25;

export interface SeriesSpecOptions {
  height: number;
  time: boolean;
  log: boolean;
  /** Vega expression of a y tick label (`axisLabelExpr`). */
  yLabels: string;
  raw: boolean;
}

const config = (p: OverviewPalette): NonNullable<VegaLiteSpec["config"]> => ({
  ...baseConfig(p),
  mark: { cursor: "default" },
});

const xEncoding = (time: boolean) => ({
  field: "x",
  type: time ? "temporal" : "quantitative",
  scale: { nice: false, zero: false },
  axis: {
    // Each tick formatted alone: an axis `format` shares one SI prefix ("0k").
    ...(time ? {} : { labelExpr: "format(datum.value, '~s')" }),
    tickCount: 3,
    grid: false,
    ticks: false,
    labelPadding: 4,
    labelFlush: true,
  },
});

const yEncoding = (field: "y" | "raw", options: SeriesSpecOptions) => ({
  field,
  type: "quantitative",
  scale: options.log ? { type: "log", nice: true } : { type: "linear", zero: false, nice: true },
  axis: {
    labelExpr: options.yLabels,
    tickCount: 4,
    grid: true,
    gridOpacity: 0.5,
    domain: false,
    ticks: false,
    labelPadding: 4,
  },
});

const lineEncoding = {
  color: { field: "color", type: "nominal", scale: null, legend: null },
  strokeDash: {
    field: "dash",
    type: "nominal",
    scale: { domain: DASH_PATTERNS.map((_, index) => String(index)), range: DASH_PATTERNS },
    legend: null,
  },
  detail: { field: "key" },
};

const positive = (field: string, log: boolean) => (log ? [{ filter: `datum.${field} > 0` }] : []);

/** One panel of series rows (`data: rows`). */
export const seriesSpec = (p: OverviewPalette, options: SeriesSpecOptions): VegaLiteSpec => {
  const x = xEncoding(options.time);
  const rawLayer = {
    transform: positive("raw", options.log),
    mark: { type: "line", strokeWidth: 1, opacity: RAW_OPACITY },
    encoding: { x, y: yEncoding("raw", options), ...lineEncoding },
  };
  return asSpec({
    height: options.height,
    autosize: { type: "fit", contains: "padding" },
    padding: { left: 0, right: 4, top: 4, bottom: 0 },
    data: { name: "rows" },
    layer: [
      ...(options.raw ? [rawLayer] : []),
      {
        transform: positive("y", options.log),
        mark: { type: "line", strokeWidth: 1.5 },
        encoding: { x, y: yEncoding("y", options), ...lineEncoding },
      },
      {
        // Invisible hit targets: a tooltip naming the line, its x and its value.
        transform: positive("y", options.log),
        mark: { type: "point", filled: true, size: 60, opacity: 0 },
        encoding: { x, y: { field: "y", type: "quantitative" }, tooltip: { field: "tip" } },
      },
    ],
    config: config(p),
  });
};

const markColors = (color: string) =>
  Object.fromEntries(
    ["mark", "line", "point", "bar", "area", "rule", "tick", "circle", "square"].map((mark) => [
      mark,
      { color },
    ]),
  );

/**
 * A run's own figure, drawn as authored but in the app's type, in its file's
 * colour, sized to the panel. Its title is dropped: the panel names it.
 */
export const figureSpec = (
  p: OverviewPalette,
  authored: Record<string, unknown>,
  color: string,
  height: number,
): VegaLiteSpec => {
  const { title: _title, width: _width, height: _height, config: own, ...rest } = authored;
  return asSpec({
    ...rest,
    height,
    autosize: { type: "fit", contains: "padding" },
    padding: { left: 0, right: 4, top: 4, bottom: 0 },
    config: {
      ...config(p),
      ...markColors(color),
      ...(own && typeof own === "object" ? own : {}),
      // Authored axis titles stay, in the app's type; no title is invented.
      axis: {
        ...config(p).axis,
        titleFont: p.font,
        titleFontSize: 11,
        titleFontWeight: "normal",
        titleColor: p.muted,
        // A narrow panel drops colliding tick labels instead of running them together.
        labelOverlap: true,
        labelSeparation: 6,
        labelFlush: true,
      },
    },
  });
};

/** The authored figure's title, when it is plain text. */
export const figureTitle = (authored: Record<string, unknown>): string | null => {
  const title = authored.title;
  if (typeof title === "string") return title;
  if (
    title &&
    typeof title === "object" &&
    typeof (title as { text?: unknown }).text === "string"
  ) {
    return (title as { text: string }).text;
  }
  return null;
};

/** Parse a `*.mlp.vl.json` file; throws when it is not a Vega-Lite object. */
export const parseFigure = (text: string): Record<string, unknown> => {
  const parsed: unknown = JSON.parse(text);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("The figure is not a Vega-Lite object.");
  }
  return parsed as Record<string, unknown>;
};
