/**
 * Sorting an attempt's metric records into the cards that show them.
 *
 * The WAL carries five record types (`t`): `scalar`, `histogram`, `text`,
 * `json` and `image_ref`. Scalars keep their own series builder
 * (`buildScalarSeries`); the other four are grouped here, one card per key.
 * Pure functions only, so the grouping is tested without a DOM.
 */

import type { BarChartConfig } from "@molcrafts/molplot";
import type { MetricRecordSample as MetricRecord } from "@/lib/contribution-types";

/** The task a record was written from (`tags.task`), if any. */
export const taskOf = (record: MetricRecord): string | null => {
  const task = record.tags?.task;
  return typeof task === "string" && task.length > 0 ? task : null;
};

/** The attempt a record was replayed from by the node cache (`tags.replayed_from`). */
export const replayedFromOf = (record: MetricRecord): string | null => {
  const source = record.tags?.replayed_from;
  return typeof source === "string" && source.length > 0 ? source : null;
};

/** Every task named by the records, sorted. Empty when none carries `tags.task`. */
export const listTasks = (records: readonly MetricRecord[]): string[] => {
  const tasks = new Set<string>();
  for (const record of records) {
    const task = taskOf(record);
    if (task) tasks.add(task);
  }
  return [...tasks].sort((left, right) => left.localeCompare(right));
};

/** The records one task wrote; `null` keeps every record. */
export const filterByTask = (
  records: readonly MetricRecord[],
  task: string | null,
): MetricRecord[] =>
  task === null ? [...records] : records.filter((record) => taskOf(record) === task);

/** The distinct `replayed_from` attempts among some records, sorted. */
export const replaySources = (records: readonly MetricRecord[]): string[] => {
  const sources = new Set<string>();
  for (const record of records) {
    const source = replayedFromOf(record);
    if (source) sources.add(source);
  }
  return [...sources].sort();
};

const stepOf = (record: MetricRecord): number | null =>
  typeof record.s === "number" && Number.isFinite(record.s) ? record.s : null;

/** One record of a card, with where it sits on the step axis. */
export interface CardEntry<V> {
  /** The record's step, or null for a record written without one. */
  step: number | null;
  wall: string | null;
  value: V;
  task: string | null;
  replayedFrom: string | null;
  /** Position in the read, the tiebreak for equal or missing steps. */
  order: number;
}

export interface MetricCard<V> {
  key: string;
  /** Entries in step order, oldest first. */
  entries: CardEntry<V>[];
  replayedFrom: string[];
}

export interface Histogram {
  bins: number[];
  counts: number[];
}

export interface ImageRef {
  path: string;
  caption: string | null;
}

export interface MetricCards {
  scalars: MetricRecord[];
  histograms: MetricCard<Histogram>[];
  texts: MetricCard<string>[];
  jsons: MetricCard<unknown>[];
  images: MetricCard<ImageRef>[];
}

const numberArray = (value: unknown): number[] | null =>
  Array.isArray(value) && value.every((item) => typeof item === "number") ? value : null;

const asHistogram = (value: unknown): Histogram | null => {
  if (!value || typeof value !== "object") return null;
  const bins = numberArray((value as { bins?: unknown }).bins);
  const counts = numberArray((value as { counts?: unknown }).counts);
  return bins && counts ? { bins, counts } : null;
};

const asImageRef = (value: unknown): ImageRef | null => {
  if (!value || typeof value !== "object") return null;
  const path = (value as { path?: unknown }).path;
  const caption = (value as { caption?: unknown }).caption;
  if (typeof path !== "string" || path.length === 0) return null;
  return { path, caption: typeof caption === "string" && caption.length > 0 ? caption : null };
};

const byStep = <V>(left: CardEntry<V>, right: CardEntry<V>): number => {
  if (left.step !== null && right.step !== null && left.step !== right.step) {
    return left.step - right.step;
  }
  return left.order - right.order;
};

const collect = <V>(
  records: readonly MetricRecord[],
  type: string,
  parse: (value: unknown) => V | null,
): MetricCard<V>[] => {
  const cards = new Map<string, CardEntry<V>[]>();
  records.forEach((record, order) => {
    if (record.t !== type || typeof record.k !== "string") return;
    const value = parse(record.v);
    if (value === null) return;
    const entries = cards.get(record.k) ?? [];
    entries.push({
      step: stepOf(record),
      wall: typeof record.w === "string" ? record.w : null,
      value,
      task: taskOf(record),
      replayedFrom: replayedFromOf(record),
      order,
    });
    cards.set(record.k, entries);
  });
  return [...cards.entries()]
    .map(([key, entries]) => {
      entries.sort(byStep);
      const sources = new Set<string>();
      for (const entry of entries) if (entry.replayedFrom) sources.add(entry.replayedFrom);
      return { key, entries, replayedFrom: [...sources].sort() };
    })
    .sort((left, right) => left.key.localeCompare(right.key));
};

/** Split records by `t` into scalars (for the series builder) and one card per key of the rest. */
export const buildMetricCards = (records: readonly MetricRecord[]): MetricCards => ({
  scalars: records.filter((record) => record.t === "scalar"),
  histograms: collect(records, "histogram", asHistogram),
  texts: collect(records, "text", (value) => (typeof value === "string" ? value : null)),
  jsons: collect(records, "json", (value) => (value === undefined ? null : value)),
  images: collect(records, "image_ref", asImageRef),
});

/** How many keys of every type the records hold — what the Metrics tab shows. */
export const countMetricKeys = (records: readonly MetricRecord[]): number => {
  const keys = new Set<string>();
  for (const record of records) {
    if (typeof record.k === "string" && typeof record.t === "string") {
      keys.add(`${record.t}\u0000${record.k}`);
    }
  }
  return keys.size;
};

/**
 * Whether an image path names a file inside the attempt.
 *
 * `image` archives into `artifacts/`, so its path is attempt-relative; a bare
 * `image_ref` may record a path from anywhere, and that is not a file this
 * attempt's file route can serve.
 */
export const isAttemptRelative = (path: string): boolean => {
  const normalized = path.replace(/\\/g, "/");
  if (normalized.startsWith("/") || /^[a-z]:\//i.test(normalized)) return false;
  return !normalized.split("/").includes("..");
};

const formatEdge = (value: number): string =>
  Number.isInteger(value) ? String(value) : Number(value.toPrecision(4)).toString();

/**
 * One histogram step as a bar chart.
 *
 * `bins` are edges when there is one more of them than counts (numpy's
 * convention, and what `ctx.metrics.histogram` documents); otherwise each bin
 * labels its own bar.
 */
export const buildHistogramBarConfig = (
  key: string,
  histogram: Histogram,
  color: string,
): BarChartConfig => {
  const { bins, counts } = histogram;
  const edges = bins.length === counts.length + 1;
  return {
    series: [
      {
        id: key,
        label: key,
        color,
        points: counts.map((count, index) => {
          const label = edges
            ? `${formatEdge(bins[index])}–${formatEdge(bins[index + 1])}`
            : formatEdge(bins[index] ?? index);
          return { x: label, y: count, text: `${label}: ${count}` };
        }),
      },
    ],
    xAxis: { label: key, dtype: "category" },
    yAxis: { label: "count" },
    bargap: 0.05,
    theme: "auto",
  };
};
