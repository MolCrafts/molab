// ─────────────────────────────────────────────────────────────────────────────
// Specs for the instrument strip faces: the success dial, the unit meter and
// the duration range. Each reads one named dataset and shares the hover/pick
// grammar in `common.ts`. Pure: no React, no DOM.
// ─────────────────────────────────────────────────────────────────────────────

import type { VegaLiteSpec } from "@molcrafts/ui-vega-lite";

import {
  asSpec,
  baseConfig,
  emphasis,
  hoverParam,
  type OverviewPalette,
  SPAN_EXPR,
  tooltip,
} from "./common";

// ── Dial ─────────────────────────────────────────────────────────────────────

export const DIAL = { width: 128, height: 100, cx: 64, cy: 58, outer: 50, inner: 40 } as const;

const SWEEP = (4 * Math.PI) / 3;
const START = -SWEEP / 2;
const GAP = 0.035;

export interface DialShare {
  key: string;
  count: number;
  color: string;
  tip: string;
}

/** Track, quarter ticks, then one arc per non-empty share — completed first, from the dial's zero. */
export const dialRows = (shares: readonly DialShare[]): Record<string, unknown>[] => {
  const total = shares.reduce((sum, share) => sum + share.count, 0);
  const present = shares.filter((share) => share.count > 0);
  const usable = SWEEP - GAP * Math.max(0, present.length - 1);
  const rows: Record<string, unknown>[] = [
    {
      key: "track",
      layer: "track",
      theta: START,
      theta2: START + SWEEP,
      r0: DIAL.inner,
      r1: DIAL.outer,
      color: null,
      tip: "",
    },
    ...[0, 0.25, 0.5, 0.75, 1].map((tick) => {
      const at = START + tick * SWEEP;
      return {
        key: `tick-${tick}`,
        layer: "tick",
        theta: at - 0.008,
        theta2: at + 0.008,
        r0: DIAL.outer + 3,
        r1: DIAL.outer + (tick === 0.5 ? 9 : 6),
        color: null,
        tip: "",
      };
    }),
  ];
  if (total === 0) return rows;
  let cursor = START;
  present.forEach((share, index) => {
    const span = (share.count / total) * usable;
    rows.push({
      key: share.key,
      layer: "segment",
      theta: cursor,
      theta2: cursor + Math.max(span, 0.01),
      r0: DIAL.inner,
      r1: DIAL.outer,
      color: share.color,
      tip: share.tip,
    });
    cursor += span + (index < present.length - 1 ? GAP : 0);
  });
  return rows;
};

const arcEncoding = {
  theta: { field: "theta", type: "quantitative", scale: null },
  theta2: { field: "theta2" },
  radius: { field: "r1", type: "quantitative", scale: null },
  radius2: { field: "r0" },
  x: { value: DIAL.cx },
  y: { value: DIAL.cy },
  color: { field: "color", type: "nominal", scale: null, legend: null },
} as const;

export const dialSpec = (p: OverviewPalette): VegaLiteSpec =>
  asSpec({
    width: DIAL.width,
    height: DIAL.height,
    autosize: { type: "none" },
    padding: 0,
    data: { name: "dial" },
    layer: [
      {
        transform: [{ filter: "datum.layer !== 'segment'" }],
        mark: { type: "arc", cursor: "default" },
        encoding: {
          ...arcEncoding,
          color: { condition: { test: "datum.layer === 'tick'", value: p.muted }, value: p.rule },
        },
      },
      {
        transform: [{ filter: "datum.layer === 'segment'" }],
        params: [hoverParam],
        mark: { type: "arc", cursor: "pointer" },
        encoding: { ...arcEncoding, opacity: emphasis, tooltip },
      },
    ],
    config: baseConfig(p),
  });

// ── Unit meter ───────────────────────────────────────────────────────────────

/** Width of one mark's column, mark plus gutter, in px. */
export const UNIT_STEP = 15;
export const UNIT_HEIGHT = 34;

export interface UnitRow {
  key: string;
  order: number;
  /** 0..1 filled share; 1 for a mark that is simply present. */
  level: number;
  levelled: boolean;
  outline: boolean;
  color: string;
  tip: string;
}

const unitX = {
  field: "order",
  type: "ordinal",
  axis: null,
  scale: { paddingInner: 0.28, paddingOuter: 0 },
} as const;
const unitY = { type: "quantitative", scale: { domain: [0, 1] }, axis: null } as const;

export const unitSpec = (p: OverviewPalette, reference: number | null): VegaLiteSpec =>
  asSpec({
    height: UNIT_HEIGHT,
    autosize: { type: "fit", contains: "padding" },
    padding: 0,
    data: { name: "units" },
    layer: [
      {
        transform: [{ filter: "datum.levelled" }],
        mark: { type: "bar", cornerRadius: 1, cursor: "default", color: p.rule, opacity: 0.6 },
        encoding: { x: unitX, y: { ...unitY, datum: 1 }, y2: { datum: 0 } },
      },
      {
        params: [hoverParam],
        mark: { type: "bar", cornerRadius: 1, strokeWidth: 1.25 },
        encoding: {
          x: unitX,
          y: { ...unitY, field: "level" },
          y2: { datum: 0 },
          fill: {
            condition: { test: "datum.outline", value: p.ground },
            field: "color",
            type: "nominal",
            scale: null,
            legend: null,
          },
          stroke: { field: "color", type: "nominal", scale: null, legend: null },
          opacity: emphasis,
          tooltip,
        },
      },
      ...(reference === null
        ? []
        : [
            {
              data: { values: [{}] },
              mark: { type: "rule", strokeDash: [2, 2], strokeWidth: 1, color: p.ink },
              encoding: { y: { ...unitY, datum: reference } },
            },
          ]),
    ],
    config: baseConfig(p),
  });

// ── Duration range ───────────────────────────────────────────────────────────

export interface DurationAxis {
  domain: [number, number];
  ticks: number[];
  log: boolean;
}

export const RANGE_HEIGHT = 30;

export const rangeSpec = (p: OverviewPalette, axis: DurationAxis): VegaLiteSpec => {
  const x = {
    type: "quantitative",
    scale: { type: axis.log ? "log" : "linear", domain: axis.domain, nice: false, zero: false },
    axis: {
      values: axis.ticks,
      labelExpr: SPAN_EXPR("datum.value"),
      grid: false,
      domain: false,
      ticks: false,
      labelPadding: 4,
    },
  } as const;
  return asSpec({
    height: RANGE_HEIGHT,
    autosize: { type: "fit", contains: "padding" },
    padding: { left: 0, right: 0, top: 4, bottom: 0 },
    data: { name: "range" },
    layer: [
      {
        data: { values: [{}] },
        mark: { type: "rule", color: p.rule, strokeWidth: 1, cursor: "default" },
        encoding: { x: { ...x, datum: axis.domain[0] }, x2: { datum: axis.domain[1] } },
      },
      {
        transform: [{ filter: "datum.part === 'whisker'" }],
        mark: { type: "rule", color: p.muted, strokeWidth: 1.5 },
        encoding: { x: { ...x, field: "from" }, x2: { field: "to" }, tooltip },
      },
      {
        transform: [{ filter: "datum.part === 'box'" }],
        mark: {
          type: "bar",
          height: 12,
          cornerRadius: 2,
          color: p.accent,
          fillOpacity: 0.22,
          stroke: p.accent,
          strokeOpacity: 0.7,
        },
        encoding: { x: { ...x, field: "from" }, x2: { field: "to" }, tooltip },
      },
      {
        transform: [{ filter: "datum.part === 'median'" }],
        mark: { type: "tick", thickness: 2.5, size: 20, color: p.ink, orient: "vertical" },
        encoding: { x: { ...x, field: "from" }, tooltip },
      },
    ],
    config: baseConfig(p),
  });
};
