/**
 * Vega-Lite specs for overview instruments. The viewer is
 * `@molcrafts/ui-vega-lite`. This module only builds the spec.
 *
 * Status is a horizontal bar, one category per row. A duration is a
 * histogram. Neither is an arc.
 */

import type { ChartTheme, VegaLiteSpec } from "@molcrafts/ui-vega-lite";

export const INSTRUMENT_MONO =
  '"JetBrains Mono", SFMono-Regular, Consolas, "Liberation Mono", monospace';

/** Vega-Lite's own pointer selection. An empty selection leaves every bar at rest. */
const hoverEncoding = (ink: string) => ({
  opacity: {
    condition: { param: "hover", value: 1 },
    value: 0.4,
  },
  stroke: {
    condition: { param: "hover", empty: false, value: ink },
    value: "transparent",
  },
  strokeWidth: {
    condition: { param: "hover", empty: false, value: 1.5 },
    value: 0,
  },
  tooltip: { field: "tooltip", type: "nominal" as const, title: "tooltip" },
});

const chartConfig = (theme: ChartTheme): VegaLiteSpec["config"] => ({
  font: INSTRUMENT_MONO,
  background: "transparent",
  view: { stroke: "transparent" },
  axis: {
    labelFont: INSTRUMENT_MONO,
    titleFont: INSTRUMENT_MONO,
    labelColor: theme.mutedForeground,
    tickColor: theme.border,
    domainColor: theme.foreground,
    gridColor: theme.border,
    grid: true,
    title: null,
  },
});

export interface BarDatum {
  id: string;
  label: string;
  value: number;
  tooltip: string;
}

/**
 * Ordinal columns. The named dataset is `bars` (`order`, `axis`, `value`).
 * `axis` may repeat a label with a zero-width suffix so blank ticks stay
 * distinct. `order` keeps the columns in data order.
 * One column is inset on the band so it stays a column. A series shares the
 * axis. Hover uses Vega's point selection: the bar under the pointer stays
 * full, the others recede, and `tooltip` is the sentence already on the row.
 */
export const barSpec = (theme: ChartTheme, single: boolean): VegaLiteSpec => {
  const axis = chartConfig(theme)?.axis;
  const rule = theme.border;
  const label = theme.mutedForeground;
  return {
    width: 360,
    height: 128,
    background: "transparent",
    autosize: { type: "fit", contains: "padding" },
    padding: { left: 4, right: 36, top: 8, bottom: 4 },
    data: { name: "bars" },
    params: [{ name: "hover", select: { type: "point", on: "pointerover", clear: "pointerout" } }],
    mark: {
      type: "bar",
      color: theme.primary,
      cursor: "pointer",
      cornerRadiusTopLeft: 2,
      cornerRadiusTopRight: 2,
    },
    encoding: {
      ...hoverEncoding(theme.foreground),
      x: {
        field: "axis",
        type: "ordinal",
        sort: { field: "order", order: "ascending" },
        scale: single
          ? { paddingInner: 0.2, paddingOuter: 1.15 }
          : { paddingInner: 0.28, paddingOuter: 0.12 },
        axis: {
          title: null,
          grid: false,
          domainColor: rule,
          tickColor: rule,
          labelColor: label,
          labelAngle: 0,
          labelOverlap: false,
          labelFlush: true,
          labelPadding: 8,
          labelLimit: 180,
          labelFontSize: 11,
          tickSize: 0,
        },
      },
      y: {
        field: "value",
        type: "quantitative",
        scale: { zero: true, nice: true },
        axis: {
          title: null,
          domain: false,
          ticks: false,
          tickCount: 3,
          tickMinStep: 1,
          format: "d",
          gridColor: rule,
          labelColor: label,
          labelFontSize: 11,
          labelPadding: 8,
        },
      },
    },
    config: {
      ...chartConfig(theme),
      axis: {
        ...axis,
        domainColor: rule,
        tickColor: rule,
        gridColor: rule,
        labelColor: label,
        labelFontSize: 11,
      },
    },
  };
};

/**
 * Status mix as horizontal bars. The named dataset is `statuses`
 * (`order`, `label`, `value`, `color`). Color is the resolved status color.
 * `fit` keeps the category names inside the chart width.
 * Hover uses the same Vega point selection as the histogram.
 */
export const statusBarSpec = (theme: ChartTheme): VegaLiteSpec => {
  const axis = chartConfig(theme)?.axis;
  const rule = theme.border;
  const ink = theme.mutedForeground;
  return {
    width: 320,
    height: 160,
    background: "transparent",
    autosize: { type: "fit", contains: "padding" },
    padding: { left: 4, right: 8, top: 4, bottom: 4 },
    data: { name: "statuses" },
    params: [{ name: "hover", select: { type: "point", on: "pointerover", clear: "pointerout" } }],
    mark: { type: "bar", cursor: "pointer", cornerRadiusEnd: 2 },
    encoding: {
      ...hoverEncoding(theme.foreground),
      y: {
        field: "label",
        type: "ordinal",
        sort: { field: "order", order: "ascending" },
        scale: { paddingInner: 0.35 },
        axis: {
          title: null,
          domain: false,
          ticks: false,
          grid: false,
          labelColor: ink,
          labelFontSize: 11,
          labelLimit: 140,
          labelPadding: 8,
        },
      },
      x: {
        field: "value",
        type: "quantitative",
        scale: { zero: true, nice: true },
        axis: {
          title: null,
          domain: false,
          ticks: false,
          tickCount: 3,
          tickMinStep: 1,
          format: "d",
          grid: true,
          gridColor: rule,
          labelColor: ink,
          labelFontSize: 11,
          labelPadding: 6,
        },
      },
      color: { field: "color", type: "nominal", scale: null, legend: null },
    },
    config: {
      ...chartConfig(theme),
      axis: {
        ...axis,
        domainColor: rule,
        tickColor: rule,
        gridColor: rule,
        labelColor: ink,
        labelFontSize: 11,
      },
    },
  };
};
