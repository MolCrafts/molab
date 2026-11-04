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

// ── Timeline ─────────────────────────────────────────────────────────────────

export const TIMELINE_ROW = 24;

/** When each run ran, on one clock, with a rule at now. Click opens the run. */
export const timelineSpec = (
  p: OverviewPalette,
  rows: number,
  window: { from: number; to: number },
  /** Draw the dashed "now" rule — only while something is still going. */
  showNow = true,
): VegaLiteSpec =>
  asSpec({
    height: Math.max(1, rows) * TIMELINE_ROW,
    autosize: { type: "fit", contains: "padding" },
    padding: { left: 16, right: 8, top: 0, bottom: 0 },
    data: { name: "spans" },
    layer: [
      {
        params: [hoverParam],
        mark: { type: "bar", height: 10, cornerRadius: 2, strokeWidth: 1 },
        encoding: {
          y: {
            field: "label",
            type: "nominal",
            sort: { field: "order", op: "min" },
            axis: groupAxis(p, 280),
          },
          x: {
            field: "start",
            type: "temporal",
            scale: { domain: [window.from, window.to] },
            axis: {
              orient: "top",
              format: clockFormat(window.to - window.from),
              tickCount: 6,
              grid: true,
              gridOpacity: 0.6,
              domain: false,
              ticks: false,
              labelPadding: 8,
            },
          },
          x2: { field: "end" },
          fill: { field: "color", type: "nominal", scale: null, legend: null },
          stroke: { field: "color", type: "nominal", scale: null, legend: null },
          opacity: emphasis,
          tooltip,
        },
      },
      ...(showNow
        ? [
            {
              data: { values: [{}] },
              mark: { type: "rule", strokeDash: [3, 3], color: p.ink, opacity: 0.7 },
              encoding: { x: { datum: window.to, type: "temporal" } },
            },
          ]
        : []),
    ],
    config: baseConfig(p),
  });

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

// ── One run among its siblings ───────────────────────────────────────────────

export const POSITION_HEIGHT = 72;

/**
 * Every finished run of the experiment on one duration axis, the run on the
 * page drawn larger and ringed (its tooltip names it). Siblings recede; hover names them,
 * click opens them. `lane` stacks coincident dots.
 */
export const positionSpec = (p: OverviewPalette, axis: DurationAxis): VegaLiteSpec => {
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
    field: "lane",
    type: "quantitative",
    scale: { domain: [-4, 4] },
    axis: null,
  } as const;
  return asSpec({
    height: POSITION_HEIGHT,
    autosize: { type: "fit", contains: "padding" },
    padding: { left: 8, right: 8, top: 16, bottom: 0 },
    data: { name: "siblings" },
    layer: [
      {
        params: [hoverParam],
        transform: [{ filter: "!datum.self" }],
        mark: { type: "point", filled: true, size: 46, strokeWidth: 1.5, stroke: p.ground },
        encoding: {
          x: { ...x, field: "seconds" },
          y,
          fill: { field: "color", type: "nominal", scale: null, legend: null },
          opacity: { condition: { param: "hover", empty: false, value: 1 }, value: 0.45 },
          tooltip,
        },
      },
      {
        transform: [{ filter: "datum.self" }],
        mark: { type: "point", filled: true, size: 150, strokeWidth: 3, stroke: p.ink },
        encoding: {
          x: { ...x, field: "seconds" },
          y: { ...y, datum: 0 },
          fill: { field: "color", type: "nominal", scale: null, legend: null },
          tooltip,
        },
      },
    ],
    config: baseConfig(p),
  });
};
