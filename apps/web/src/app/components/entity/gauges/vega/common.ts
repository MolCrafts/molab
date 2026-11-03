// ─────────────────────────────────────────────────────────────────────────────
// One interaction grammar for every overview chart, so a reader learns it once:
//  · hover — the mark (or the row it belongs to) stays full, the rest recede,
//    and a one-sentence tooltip names it;
//  · click — `pick` reports the mark's `key`; the page decides what it opens;
//  · drag — charts on a time axis report a `brush` window.
// Every row a chart reads carries `key` (identity) and `tip` (the sentence).
// Colours arrive resolved: Vega cannot paint `var(--status-*)`.
// ─────────────────────────────────────────────────────────────────────────────

import type { ChartTheme, VegaLiteSpec } from "@molcrafts/ui-vega-lite";

import type { StatusGroupId } from "@/app/runs/statusGroups";

import { INSTRUMENT_MONO } from "../../instruments";

export interface OverviewPalette {
  status: Record<StatusGroupId, string>;
  accent: string;
  ink: string;
  muted: string;
  rule: string;
  ground: string;
  font: string;
}

export const paletteOf = (
  theme: ChartTheme,
  status: Record<StatusGroupId, string>,
  read: (name: string, fallback: string) => string,
): OverviewPalette => ({
  status,
  accent: read("--molab-accent", theme.primary),
  ink: read("--molab-foreground", theme.foreground),
  muted: read("--molab-muted-foreground", theme.mutedForeground),
  rule: read("--molab-border", theme.border),
  ground: read("--molab-background", theme.background),
  font: theme.font,
});

export const MONO = INSTRUMENT_MONO;

export const hoverParam = {
  name: "hover",
  select: { type: "point", on: "pointerover", clear: "pointerout", fields: ["key"] },
} as const;

/** The hovered mark stays full; with nothing hovered every mark rests at full ink. */
export const emphasis = { condition: { param: "hover", value: 1 }, value: 0.32 } as const;

/** Emphasis plus a held choice: a row marked `faded` stays receded until the choice is cleared. */
export const heldEmphasis = {
  condition: [
    { test: "datum.faded", value: 0.3 },
    { param: "hover", value: 1 },
  ],
  value: 0.32,
} as const;

export const tooltip = { field: "tip", type: "nominal", title: "tooltip" } as const;

/** Seconds as a person reads them, in a Vega expression: 45s · 12m · 1h 20m · 2.5d. */
export const SPAN_EXPR = (value: string): string =>
  `${value} < 60 ? format(${value}, '.0f') + 's' : ` +
  `${value} < 3600 ? format(${value} / 60, '.0f') + 'm' : ` +
  `${value} < 86400 ? floor(${value} / 3600) + 'h' + (${value} % 3600 >= 60 ? ' ' + format((${value} % 3600) / 60, '.0f') + 'm' : '') : ` +
  `format(${value} / 86400, '.1f') + 'd'`;

export const baseConfig = (p: OverviewPalette): NonNullable<VegaLiteSpec["config"]> => ({
  font: p.font,
  background: "transparent",
  view: { stroke: "transparent" },
  axis: {
    labelFont: MONO,
    labelFontSize: 10,
    labelColor: p.muted,
    domainColor: p.rule,
    tickColor: p.rule,
    gridColor: p.rule,
    title: null,
  },
  // The brush is a quiet wash in the accent, never a grey box.
  mark: { cursor: "pointer" },
});

/** A clicked scenegraph item → the key of the row it draws, if it draws one. */
export const clickedKey = (item: unknown): string | null => {
  const datum = (item as { datum?: { key?: unknown } } | null | undefined)?.datum;
  return datum?.key == null ? null : String(datum.key);
};

/** Interval value → [from, to] in epoch ms. Vega reports `{ <field>: [a, b] }`, or `{}`. */
export const brushedWindow = (value: unknown, field: string): [number, number] | null => {
  if (!value || typeof value !== "object") return null;
  const range = (value as Record<string, unknown>)[field];
  if (!Array.isArray(range) || range.length < 2) return null;
  const from = Number(new Date(range[0] as string | number));
  const to = Number(new Date(range[1] as string | number));
  if (!Number.isFinite(from) || !Number.isFinite(to) || from === to) return null;
  return from < to ? [from, to] : [to, from];
};

/** Typed escape hatch: specs are authored as plain objects and checked by compiling them in tests. */
export const asSpec = (spec: object): VegaLiteSpec => spec as VegaLiteSpec;
