/**
 * The data behind `<molab-metric-chart>`: one row per run on the swept axis,
 * in the row shape `sweepSpec` (the experiment Overview's key-result chart)
 * draws — plus `failed`, which the page's chart adds as a ✗ at the run's x.
 */

import type { VegaLiteSpec } from "@molcrafts/ui-vega-lite";
import { sweepSpec } from "@/app/components/entity/gauges/vega/chartSpecs";
import { asSpec, type OverviewPalette, tooltip } from "@/app/components/entity/gauges/vega/common";
import { formatParameter, formatParameterValue, runLabel } from "@/app/runs/runTitle";
import { normalizeStatus } from "@/app/status/vocabulary";
import { runValue } from "./runQuery";

export interface MetricRun {
  id: string;
  name?: string;
  title?: string;
  status: string;
  parameters: Record<string, unknown>;
}

export interface MetricAxes {
  x: string;
  y: string;
  by?: string;
}

// A type alias, not an interface: Vega datasets need an implicit index signature.
export type MetricRow = {
  key: string;
  x: string;
  xOrder: number;
  /** The metric; null for a failed run (drawn as ✗ at the top of the axis). */
  y: number | null;
  plotY: number;
  series: string;
  self: false;
  own: true;
  failed: boolean;
  /** The series name, at its last point; null elsewhere. */
  label: string | null;
  tip: string;
};

export interface MetricAxis {
  labels: string[];
  log: boolean;
  domain: [number, number];
  small: boolean;
}

export interface MetricChartData {
  rows: MetricRow[];
  axis: MetricAxis;
  /** Runs with a value of y. */
  withValue: number;
}

const numeric = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

const compareValues = (left: unknown, right: unknown): number =>
  numeric(left) && numeric(right) ? left - right : String(left).localeCompare(String(right));

const axisOf = (labels: string[], ys: readonly number[]): MetricAxis => {
  if (ys.length === 0) return { labels, log: false, domain: [0, 1], small: false };
  const low = Math.min(...ys);
  const high = Math.max(...ys);
  const log = low > 0 && high / low > 30;
  const pad = (high - low || Math.abs(low) || 1) * 0.1;
  const domain: [number, number] = log ? [low / 1.6, high * 1.6] : [low - pad, high + pad];
  return { labels, log, domain, small: Math.max(Math.abs(low), Math.abs(high)) < 1e-2 };
};

/** Each series named once, at its rightmost point. */
const seriesLabels = (rows: readonly Omit<MetricRow, "label" | "plotY">[]): Map<string, string> => {
  const last = new Map<string, { key: string; order: number }>();
  for (const row of rows) {
    if (row.y === null) continue;
    const current = last.get(row.series);
    if (!current || row.xOrder >= current.order) {
      last.set(row.series, { key: row.key, order: row.xOrder });
    }
  }
  return new Map([...last].map(([series, { key }]) => [key, series]));
};

/**
 * y against x across *runs*, one series per value of `by`. A run without x
 * is left out; a run without y is left out unless it failed.
 */
export const metricChartData = (
  runs: readonly MetricRun[],
  axes: MetricAxes,
  resultsOf: (runId: string) => Readonly<Record<string, unknown>> | null | undefined,
): MetricChartData => {
  const placed = runs.filter((run) => axes.x in run.parameters);
  const values = [
    ...new Map(
      placed.map((run) => [JSON.stringify(run.parameters[axes.x]), run.parameters[axes.x]]),
    ).values(),
  ].sort(compareValues);
  const labels = values.map((value) => formatParameterValue(axes.x, value));
  const base = placed.flatMap((run) => {
    const raw = runValue(run.parameters, resultsOf(run.id), axes.y);
    const failed = normalizeStatus(run.status) === "failed";
    const y = numeric(raw) && !failed ? raw : null;
    if (y === null && !failed) return [];
    const value = run.parameters[axes.x];
    const by = axes.by;
    return [
      {
        key: run.id,
        x: formatParameterValue(axes.x, value),
        xOrder: values.findIndex((candidate) => compareValues(candidate, value) === 0),
        y,
        series: by && by in run.parameters ? formatParameter(by, run.parameters[by]) : "all runs",
        self: false as const,
        own: true as const,
        failed,
        tip: `${runLabel(run)} · ${y === null ? "failed" : `${axes.y} ${y.toPrecision(3)}`}`,
      },
    ];
  });
  const axis = axisOf(
    labels,
    base.flatMap((row) => (row.y === null ? [] : [row.y])),
  );
  const named = axes.by ? seriesLabels(base) : new Map<string, string>();
  return {
    rows: base.map((row) => ({
      ...row,
      plotY: row.y ?? axis.domain[1],
      label: named.get(row.key) ?? null,
    })),
    axis,
    withValue: base.filter((row) => row.y !== null).length,
  };
};

type LayeredSpec = VegaLiteSpec & {
  layer: { encoding?: { x?: unknown; y?: unknown } }[];
};

/** The Overview's sweep spec, plus failed runs as ✗ on the same x and y scales. */
export const metricSpec = (palette: OverviewPalette, axis: MetricAxis): VegaLiteSpec => {
  const sweep = sweepSpec(palette, axis) as LayeredSpec;
  const encoding = sweep.layer[0]?.encoding ?? {};
  const failures = {
    transform: [{ filter: "datum.failed" }],
    mark: {
      type: "point",
      shape: "cross",
      angle: 45,
      filled: true,
      size: 72,
      color: palette.status.failed,
    },
    encoding: { x: encoding.x, y: encoding.y, tooltip },
  };
  return asSpec({ ...sweep, layer: [...sweep.layer, failures] });
};
