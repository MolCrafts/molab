// ─────────────────────────────────────────────────────────────────────────────
// Specs for the overview's full-width charts: activity (with a time brush), the
// status mix per group, durations per group, and the run timeline. Same
// hover/pick grammar as the instruments. Pure: no React, no DOM.
// ─────────────────────────────────────────────────────────────────────────────

import type { VegaLiteSpec } from "@molcrafts/ui-vega-lite";

import {
  asSpec,
  baseConfig,
  emphasis,
  heldEmphasis,
  hoverParam,
  MONO as MONO_FONT,
  type OverviewPalette,
  SPAN_EXPR,
  tooltip,
} from "./common";
import type { DurationAxis } from "./instrumentSpecs";

const clockFormat = (spanMs: number): string => (spanMs <= 36 * 60 * 60 * 1000 ? "%H:%M" : "%a %d");

const groupAxis = (p: OverviewPalette, limit: number) => ({
  title: null,
  domain: false,
  ticks: false,
  labelFont: p.font,
  labelFontSize: 12,
  labelColor: p.ink,
  labelLimit: limit,
  labelPadding: 12,
});

// ── Activity ─────────────────────────────────────────────────────────────────

export const ACTIVITY_HEIGHT = 200;

/**
 * Starts rise above the axis, finishes hang below it stacked by outcome.
 * Hover lights a whole time bucket; dragging selects a window (`brush`).
 */
export const activitySpec = (
  p: OverviewPalette,
  window: { from: number; to: number },
): VegaLiteSpec =>
  asSpec({
    height: ACTIVITY_HEIGHT,
    autosize: { type: "fit", contains: "padding" },
    padding: { left: 0, right: 4, top: 4, bottom: 0 },
    data: { name: "activity" },
    layer: [
      {
        params: [
          hoverParam,
          {
            name: "brush",
            select: {
              type: "interval",
              encodings: ["x"],
              mark: {
                fill: p.accent,
                fillOpacity: 0.1,
                stroke: p.accent,
                strokeOpacity: 0.6,
                strokeWidth: 1,
              },
            },
          },
        ],
        mark: { type: "rect", cornerRadius: 1 },
        encoding: {
          x: {
            field: "start",
            type: "temporal",
            scale: { domain: [window.from, window.to] },
            axis: {
              format: clockFormat(window.to - window.from),
              tickCount: 6,
              grid: false,
              domain: false,
              ticks: false,
              labelPadding: 8,
              labelFlush: true,
            },
          },
          x2: { field: "end" },
          y: {
            field: "y0",
            type: "quantitative",
            axis: {
              // Which side is which: starts rise, finishes hang (L01 decision 4).
              title: "finished ↓   started ↑",
              titleFont: p.font,
              titleFontSize: 11,
              titleFontWeight: "normal",
              titleColor: p.muted,
              titlePadding: 8,
              labelExpr: "abs(datum.value)",
              tickCount: 4,
              tickMinStep: 1,
              grid: true,
              gridOpacity: 0.6,
              domain: false,
              ticks: false,
              labelPadding: 8,
            },
          },
          y2: { field: "y1" },
          color: {
            condition: { test: "datum.kind === 'started'", value: p.muted },
            field: "color",
            type: "nominal",
            scale: null,
            legend: null,
          },
          fillOpacity: { condition: { test: "datum.kind === 'started'", value: 0.45 }, value: 1 },
          opacity: emphasis,
          tooltip,
        },
      },
      {
        data: { values: [{}] },
        mark: { type: "rule", color: p.ink, strokeWidth: 1, opacity: 0.7 },
        encoding: { y: { datum: 0 } },
      },
    ],
    config: baseConfig(p),
  });

// ── Status mix per group ─────────────────────────────────────────────────────

export const MIX_ROW = 30;

/**
 * One normalised bar per group, segments in status order, the group's total and
 * failure share printed past its end. Hover lights the group; click picks it.
 */
export const mixSpec = (p: OverviewPalette, rows: number): VegaLiteSpec => {
  const y = {
    field: "group",
    type: "nominal",
    sort: { field: "gorder", op: "min" },
    axis: groupAxis(p, 150),
  } as const;
  return asSpec({
    height: Math.max(1, rows) * MIX_ROW,
    autosize: { type: "fit", contains: "padding" },
    padding: { left: 4, right: 112, top: 0, bottom: 0 },
    data: { name: "mix" },
    layer: [
      {
        params: [hoverParam],
        mark: { type: "bar", height: 8, cornerRadius: 1, strokeWidth: 1 },
        encoding: {
          y,
          x: { field: "count", type: "quantitative", stack: "normalize", axis: null },
          order: { field: "sorder" },
          fill: {
            condition: { test: "datum.outline", value: p.ground },
            field: "color",
            type: "nominal",
            scale: null,
            legend: null,
          },
          stroke: { field: "color", type: "nominal", scale: null, legend: null },
          opacity: heldEmphasis,
          tooltip,
        },
      },
      {
        transform: [{ filter: "datum.sorder === 0" }],
        mark: { type: "text", align: "left", baseline: "middle", dx: 12, fontSize: 12 },
        encoding: {
          y,
          x: { datum: 1 },
          text: { field: "summary" },
          color: { condition: { test: "datum.alarm", value: p.status.failed }, value: p.muted },
          opacity: heldEmphasis,
        },
      },
    ],
    config: baseConfig(p),
  });
};

export const STATUS_BAR_HEIGHT = 14;

/**
 * One group's status composition as a single stacked bar, for a Preview-width
 * column (the mix layout needs ~560px for its labels). Counts are in the
 * tooltip; the key under it names the colours.
 */
export const statusBarSpec = (p: OverviewPalette): VegaLiteSpec =>
  asSpec({
    height: STATUS_BAR_HEIGHT,
    autosize: { type: "fit", contains: "padding" },
    padding: 0,
    data: { name: "mix" },
    mark: { type: "bar", height: STATUS_BAR_HEIGHT, strokeWidth: 1 },
    encoding: {
      x: { field: "count", type: "quantitative", stack: "normalize", axis: null },
      order: { field: "sorder" },
      fill: {
        condition: { test: "datum.outline", value: p.ground },
        field: "color",
        type: "nominal",
        scale: null,
        legend: null,
      },
      // An outlined state (queued) keeps its colour as the stroke, or it would vanish.
      stroke: {
        condition: { test: "datum.outline", field: "color", type: "nominal", scale: null },
        value: p.ground,
      },
      tooltip,
    },
    config: baseConfig(p),
  });

// ── Durations per group ──────────────────────────────────────────────────────

export const DURATION_ROW = 44;

/**
 * Every finished run is a dot on a shared duration axis; the band is the middle
 * half, the rule the median. Rows are a continuous y (`row` = group index plus a
 * lane offset), so stacked dots stay inside their group's row.
 */
export const durationSpec = (
  p: OverviewPalette,
  axis: DurationAxis,
  groups: readonly string[],
): VegaLiteSpec => {
  const x = {
    type: "quantitative",
    scale: { type: axis.log ? "log" : "linear", domain: axis.domain, nice: false, zero: false },
    axis: {
      values: axis.ticks,
      labelExpr: SPAN_EXPR("datum.value"),
      grid: true,
      gridOpacity: 0.6,
      domain: false,
      ticks: false,
      labelPadding: 8,
    },
  } as const;
  const y = {
    type: "quantitative",
    scale: { domain: [groups.length - 0.5, -0.5], nice: false, zero: false },
    axis: {
      ...groupAxis(p, 150),
      values: groups.map((_, index) => index),
      labelExpr: `${JSON.stringify(groups)}[datum.value]`,
      grid: false,
    },
  } as const;
  const perGroup = (ops: Array<{ op: string; as: string }>) => [
    {
      aggregate: ops.map(({ op, as }) => ({ op, field: "seconds", as })),
      groupby: ["group", "gorder"],
    },
  ];
  return asSpec({
    height: Math.max(1, groups.length) * DURATION_ROW,
    autosize: { type: "fit", contains: "padding" },
    padding: { left: 4, right: 8, top: 0, bottom: 0 },
    data: { name: "durations" },
    layer: [
      {
        transform: perGroup([
          { op: "q1", as: "q1" },
          { op: "q3", as: "q3" },
        ]),
        mark: { type: "bar", height: 14, cornerRadius: 2, color: p.rule, opacity: 0.7 },
        encoding: { y: { ...y, field: "gorder" }, x: { ...x, field: "q1" }, x2: { field: "q3" } },
      },
      {
        transform: [
          ...perGroup([{ op: "median", as: "median" }]),
          { calculate: `datum.group + ' · median ' + (${SPAN_EXPR("datum.median")})`, as: "tip" },
        ],
        mark: { type: "tick", thickness: 2, size: 22, color: p.ink },
        encoding: { y: { ...y, field: "gorder" }, x: { ...x, field: "median" }, tooltip },
      },
      {
        params: [hoverParam],
        mark: { type: "point", filled: true, size: 52, strokeWidth: 1.5, stroke: p.ground },
        encoding: {
          y: { ...y, field: "row" },
          x: { ...x, field: "seconds" },
          fill: { field: "color", type: "nominal", scale: null, legend: null },
          opacity: emphasis,
          tooltip,
        },
      },
    ],
    config: baseConfig(p),
  });
};

// ── Counts per category ──────────────────────────────────────────────────────

export const BAR_ROW = 28;
/** Column pitch of a vertical bar chart: one category, its bar and its gutter. */
export const BAR_STEP = 56;

/**
 * One bar per category, in the accent (a magnitude, not a status). Vertical
 * reads an ordered series (asset versions); horizontal reads named categories
 * (task types). `label` is the axis text; the value is printed past the bar.
 */
export const barsSpec = (
  p: OverviewPalette,
  orientation: "vertical" | "horizontal",
  rows: number,
  valueExpr: string,
): VegaLiteSpec => {
  const horizontal = orientation === "horizontal";
  const category = {
    field: "label",
    type: "nominal",
    sort: { field: "order", op: "min" },
    axis: horizontal
      ? groupAxis(p, 180)
      : {
          title: null,
          domain: false,
          ticks: false,
          labelAngle: 0,
          labelPadding: 8,
          labelFont: MONO_FONT,
        },
  } as const;
  const magnitude = {
    field: "value",
    type: "quantitative",
    axis: horizontal
      ? null
      : {
          labelExpr: valueExpr,
          tickCount: 3,
          grid: true,
          gridOpacity: 0.6,
          domain: false,
          ticks: false,
          labelPadding: 8,
        },
  } as const;
  return asSpec({
    height: horizontal ? Math.max(1, rows) * BAR_ROW : 180,
    // A vertical series is laid out by step, not stretched: two versions stay two columns.
    ...(horizontal ? {} : { width: { step: BAR_STEP } }),
    autosize: horizontal ? { type: "fit", contains: "padding" } : { type: "pad" },
    padding: { left: 4, right: horizontal ? 72 : 8, top: 4, bottom: 0 },
    data: { name: "bars" },
    layer: [
      {
        params: [hoverParam],
        mark: {
          type: "bar",
          color: p.accent,
          cornerRadius: 2,
          ...(horizontal ? { height: 10 } : { width: { band: 0.6 } }),
        },
        encoding: {
          ...(horizontal ? { y: category, x: magnitude } : { x: category, y: magnitude }),
          opacity: emphasis,
          tooltip,
        },
      },
      ...(horizontal
        ? [
            {
              mark: { type: "text", align: "left", baseline: "middle", dx: 8, fontSize: 12 },
              encoding: {
                y: category,
                x: magnitude,
                text: { field: "readout" },
                color: { value: p.muted },
                opacity: emphasis,
              },
            },
          ]
        : []),
    ],
    config: baseConfig(p),
  });
};

// ── Tasks on a clock ─────────────────────────────────────────────────────────

export const CLOCK_ROW = 24;
/** What the time axis takes below the rows (label + padding). */
export const CLOCK_AXIS = 18;

/**
 * One attempt's tasks on its clock (L04): neutral bars, the status only as a
 * mark at the end (a failure's red tick), live work in the running colour to
 * now, and a word where a task that never started would be. Row labels live
 * beside the chart (glyph + name), so the y axis draws nothing.
 */
export const taskClockSpec = (
  p: OverviewPalette,
  rows: number,
  window: { from: number; to: number },
): VegaLiteSpec => {
  const y = {
    field: "order",
    type: "ordinal",
    scale: { paddingInner: 0, paddingOuter: 0 },
    axis: null,
  } as const;
  const x = {
    type: "temporal",
    scale: { domain: [window.from, window.to] },
    axis: {
      orient: "bottom",
      format: clockFormat(window.to - window.from),
      tickCount: 5,
      labelOverlap: "greedy",
      labelSeparation: 12,
      labelFlush: true,
      grid: true,
      gridOpacity: 0.5,
      domain: false,
      ticks: false,
      labelPadding: 8,
    },
  } as const;
  return asSpec({
    height: Math.max(1, rows) * CLOCK_ROW,
    autosize: { type: "fit", contains: "padding" },
    // Fit takes the axis out of the height it is given (rows + CLOCK_AXIS), leaving 24px a row.
    padding: { left: 0, right: 48, top: 0, bottom: 0 },
    data: { name: "tasks" },
    layer: [
      {
        params: [hoverParam],
        transform: [{ filter: "datum.bar" }],
        mark: { type: "bar", height: 8, cornerRadius: 1 },
        encoding: {
          y,
          x: { ...x, field: "start" },
          x2: { field: "end" },
          fill: {
            condition: { test: "datum.live", value: p.status.running },
            value: p.muted,
          },
          fillOpacity: { condition: { test: "datum.live", value: 0.9 }, value: 0.45 },
          opacity: emphasis,
          tooltip,
        },
      },
      {
        transform: [{ filter: "datum.bar && datum.mark" }],
        mark: { type: "tick", orient: "vertical", thickness: 2, size: 14 },
        encoding: {
          y,
          x: { ...x, field: "end" },
          color: { field: "mark", type: "nominal", scale: null, legend: null },
          tooltip,
        },
      },
      {
        transform: [{ filter: "!datum.bar" }],
        mark: { type: "text", align: "left", baseline: "middle", dx: 6, fontSize: 11 },
        encoding: {
          y,
          x: { ...x, field: "anchor" },
          text: { field: "note" },
          color: { value: p.muted },
        },
      },
    ],
    config: baseConfig(p),
  });
};

// ── One run among its siblings, on the swept axis ────────────────────────────

export const SWEEP_HEIGHT = 168;

/**
 * The experiment's key result along its swept parameter (L04): one line per
 * combination of the other varying values, the run's own line in the accent
 * and its point ringed. A run without the result (failed, still going) sits
 * at the top edge in its status colour. Hover names a run, click opens it.
 */
export const sweepSpec = (
  p: OverviewPalette,
  axis: { labels: string[]; log: boolean; domain: [number, number]; small: boolean },
): VegaLiteSpec => {
  // A quantitative axis over the swept values' order, labelled with the values:
  // a discrete scale would size the chart by its own step instead of the column.
  const x = {
    field: "xOrder",
    type: "quantitative",
    scale: {
      domain: [-0.25, Math.max(1, axis.labels.length - 1) + 0.25],
      nice: false,
      zero: false,
    },
    axis: {
      values: axis.labels.map((_label, index) => index),
      labelExpr: `${JSON.stringify(axis.labels)}[datum.value]`,
      domain: false,
      ticks: false,
      grid: true,
      gridOpacity: 0.5,
      labelPadding: 8,
    },
  } as const;
  const y = {
    field: "plotY",
    type: "quantitative",
    scale: { type: axis.log ? "log" : "linear", domain: axis.domain, nice: false, zero: false },
    axis: {
      labelExpr:
        axis.log || axis.small
          ? "datum.value == 0 ? '0' : format(datum.value, '.1~e')"
          : "format(datum.value, '~g')",
      tickCount: 3,
      grid: true,
      gridOpacity: 0.5,
      domain: false,
      ticks: false,
      labelPadding: 6,
    },
  } as const;
  return asSpec({
    height: SWEEP_HEIGHT,
    autosize: { type: "fit", contains: "padding" },
    padding: { left: 0, right: 96, top: 12, bottom: 0 },
    data: { name: "points" },
    layer: [
      {
        transform: [{ filter: "datum.y != null && !datum.own" }],
        mark: { type: "line", strokeWidth: 1, color: p.muted, opacity: 0.55 },
        encoding: { x, y, detail: { field: "series" } },
      },
      {
        transform: [{ filter: "datum.y != null && datum.own" }],
        mark: { type: "line", strokeWidth: 2, color: p.accent },
        // One line per series: on an experiment's chart every series is "own".
        encoding: { x, y, detail: { field: "series" } },
      },
      {
        params: [hoverParam],
        transform: [{ filter: "datum.y != null && !datum.self" }],
        mark: { type: "point", filled: true, size: 28 },
        encoding: {
          x,
          y,
          fill: { condition: { test: "datum.own", value: p.accent }, value: p.muted },
          opacity: emphasis,
          tooltip,
        },
      },
      {
        transform: [{ filter: "datum.self" }],
        mark: { type: "point", filled: true, size: 110, strokeWidth: 2.5, stroke: p.ink },
        encoding: {
          x,
          y,
          fill: { field: "color", type: "nominal", scale: null, legend: null },
          tooltip,
        },
      },
      {
        transform: [{ filter: "datum.label != null" }],
        mark: {
          type: "text",
          align: "left",
          baseline: "middle",
          dx: 8,
          fontSize: 10,
          font: MONO_FONT,
        },
        encoding: {
          x,
          y,
          text: { field: "label" },
          color: { condition: { test: "datum.own", value: p.ink }, value: p.muted },
        },
      },
    ],
    config: baseConfig(p),
  });
};

// ── One result across compared runs ─────────────────────────────────────────

export const COMPARE_ROW = 28;

/**
 * One result per compared run (L05-5): a bar per run on one axis — log when it
 * spans decades — a dashed rule at the baseline's value, and the value printed
 * past the bar. A run without the result says so in words where its bar would
 * be. Hover names the run, click opens its Preview.
 */
export const compareBarsSpec = (
  p: OverviewPalette,
  rows: number,
  axis: { domain: [number, number]; log: boolean; baseline: number | null },
): VegaLiteSpec => {
  const y = {
    field: "label",
    type: "nominal",
    sort: { field: "order", op: "min" },
    axis: { ...groupAxis(p, 240), labelFont: MONO_FONT, labelFontSize: 11 },
  } as const;
  const x = {
    type: "quantitative",
    scale: { type: axis.log ? "log" : "linear", domain: axis.domain, nice: false, zero: !axis.log },
    axis: {
      labelExpr:
        axis.log || Math.abs(axis.domain[1]) < 1e-2
          ? "datum.value == 0 ? '0' : format(datum.value, '.1~e')"
          : "format(datum.value, '~g')",
      tickCount: 4,
      grid: true,
      gridOpacity: 0.5,
      domain: false,
      ticks: false,
      labelPadding: 6,
    },
  } as const;
  return asSpec({
    height: Math.max(1, rows) * COMPARE_ROW,
    autosize: { type: "fit", contains: "padding" },
    padding: { left: 0, right: 80, top: 4, bottom: 0 },
    data: { name: "bars" },
    layer: [
      {
        params: [hoverParam],
        transform: [{ filter: "datum.value != null" }],
        mark: { type: "bar", height: 10, cornerRadius: 1, color: p.accent },
        encoding: {
          y,
          x: { ...x, field: "value" },
          x2: { datum: axis.domain[0] },
          opacity: emphasis,
          tooltip,
        },
      },
      {
        transform: [{ filter: "datum.value != null" }],
        mark: {
          type: "text",
          align: "left",
          baseline: "middle",
          dx: 6,
          fontSize: 10,
          font: MONO_FONT,
          color: p.ink,
        },
        encoding: { y, x: { ...x, field: "value" }, text: { field: "printed" } },
      },
      {
        transform: [{ filter: "datum.value == null" }],
        mark: { type: "text", align: "left", baseline: "middle", dx: 4, fontSize: 11 },
        encoding: {
          y,
          x: { ...x, datum: axis.domain[0] },
          text: { field: "printed" },
          color: { field: "color", type: "nominal", scale: null, legend: null },
        },
      },
      ...(axis.baseline === null
        ? []
        : [
            {
              data: { values: [{}] },
              mark: { type: "rule", strokeDash: [3, 3], color: p.ink, opacity: 0.6 },
              encoding: { x: { ...x, datum: axis.baseline } },
            },
          ]),
    ],
    config: baseConfig(p),
  });
};
