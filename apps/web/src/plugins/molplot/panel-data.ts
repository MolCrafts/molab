/**
 * The Style panel's settings, and a panel's lines turned into the rows its
 * Vega chart draws. Pure: no React, no DOM.
 *
 * Per line: normalise (when the panel is), then drop spikes, then smooth —
 * a lone glitch must not yank the EMA. The raw values travel beside the
 * processed ones so the raw trace can sit faded behind the smoothed line.
 */

import { normalizeSeries } from "./aggregateSeries";
import type { PanelLine, PanelModel } from "./figure-model";
import {
  DEFAULT_SCALAR_FORMAT,
  formatScalar,
  type ScalarFormat,
  type ScalarNotation,
} from "./scalar-format";
import { filterSpikes, smoothEma } from "./smoothing";

export type XAxis = "step" | "time";
export type YAxis = "linear" | "log";

export interface MolplotStyle {
  /** EMA weight, 0 (raw) … 0.99. */
  smoothing: number;
  /** Draw the raw trace behind a smoothed or filtered line. */
  raw: boolean;
  spikeFilter: boolean;
  /** Spike threshold in robust σ. */
  spikeSigma: number;
  x: XAxis;
  y: YAxis;
  notation: ScalarNotation;
  digits: number;
  /** Records of one task; null for every task. */
  task: string | null;
}

export const DEFAULT_STYLE: MolplotStyle = {
  smoothing: 0.6,
  raw: true,
  spikeFilter: false,
  spikeSigma: 4,
  x: "step",
  y: "linear",
  notation: DEFAULT_SCALAR_FORMAT.notation,
  digits: DEFAULT_SCALAR_FORMAT.significantDigits,
  task: null,
};

export const scalarFormatOf = (style: MolplotStyle): ScalarFormat => ({
  notation: style.notation,
  significantDigits: style.digits,
});

/**
 * A Vega expression formatting one y-axis tick by Notation and Digits. Auto
 * keeps plain numbers below 1000 (0.8, not "800m") and SI prefixes above
 * (-1.089k).
 */
export const axisLabelExpr = (style: MolplotStyle): string => {
  const digits = Math.min(8, Math.max(1, Math.round(style.digits)));
  const value = "datum.value";
  if (style.notation === "scientific") return `format(${value}, '.${Math.max(0, digits - 1)}e')`;
  if (style.notation === "decimal") return `format(${value}, '.${digits}~r')`;
  return `abs(${value}) >= 1000 ? format(${value}, '.${digits}~s') : format(${value}, '.${digits}~g')`;
};

/** The line is processed, so a raw trace means something behind it. */
export const isProcessed = (style: MolplotStyle): boolean =>
  style.smoothing > 0 || style.spikeFilter;

/** Draw the faded raw trace. */
export const showsRaw = (style: MolplotStyle): boolean => style.raw && isProcessed(style);

const allPositive = (panel: PanelModel): boolean =>
  panel.lines.every((line) => line.series.points.every((point) => point.y > 0));

/**
 * Log needs positive values: a panel with a value at or below zero (an
 * energy, say) stays linear rather than drawing nothing, and a normalised
 * panel spans [0, 1] and stays linear too.
 */
export const logAxis = (style: MolplotStyle, panel: PanelModel): boolean =>
  style.y === "log" && !panel.normalised && allPositive(panel);

/** The panel's note, saying when Log was asked for but could not be drawn. */
export const panelNote = (style: MolplotStyle, panel: PanelModel): string | undefined => {
  const refused = style.y === "log" && !panel.normalised && !allPositive(panel);
  const notes = [panel.note, refused ? "linear: values ≤ 0" : null].filter(Boolean);
  return notes.length > 0 ? notes.join(" · ") : undefined;
};

/** Dash patterns by index: solid, dashed, dotted, dash-dot. */
export const DASH_PATTERNS: readonly (readonly number[])[] = [
  [1, 0],
  [4, 3],
  [1, 3],
  [6, 2, 1, 2],
];

/** A type, not an interface: Vega's data rows need an index signature. */
export type PanelRow = {
  key: string;
  label: string;
  x: number;
  raw: number;
  y: number;
  color: string;
  dash: string;
  tip: string;
};

/** Raw and processed values of one line, in point order. */
export const processLine = (
  values: readonly number[],
  normalised: boolean,
  style: MolplotStyle,
): { raw: number[]; y: number[] } => {
  const raw = normalised ? normalizeSeries(values, "minmax") : [...values];
  const cleaned = style.spikeFilter ? filterSpikes(raw, { nSigma: style.spikeSigma }) : raw;
  return { raw, y: style.smoothing > 0 ? smoothEma(cleaned, style.smoothing) : cleaned };
};

const xLabel = (x: number, axis: XAxis): string =>
  axis === "time" ? new Date(x).toLocaleString() : `step ${x}`;

const lineRows = (line: PanelLine, normalised: boolean, style: MolplotStyle): PanelRow[] => {
  // A Time axis draws only what measured a wall clock; a position is no time.
  if (style.x === "time" && !line.series.timed) return [];
  const points = line.series.points;
  const { raw, y } = processLine(
    points.map((point) => point.y),
    normalised,
    style,
  );
  const format = scalarFormatOf(style);
  return points.map((point, index) => {
    const x = style.x === "time" ? point.wall : point.step;
    return {
      key: line.id,
      label: line.label,
      x,
      raw: raw[index],
      y: y[index],
      color: line.color,
      dash: String(line.dash % DASH_PATTERNS.length),
      tip: `${line.label} · ${xLabel(x, style.x)} · ${formatScalar(point.y, format)}`,
    };
  });
};

/** Every row of a panel's chart. */
export const panelRows = (panel: PanelModel, style: MolplotStyle): PanelRow[] =>
  panel.lines.flatMap((line) => lineRows(line, panel.normalised, style));

/** The latest value a panel shows in its header, when its values are its own. */
export const panelValue = (panel: PanelModel, style: MolplotStyle): string | undefined => {
  const first = panel.lines[0];
  return first && !panel.normalised
    ? formatScalar(first.series.latest, scalarFormatOf(style))
    : undefined;
};
