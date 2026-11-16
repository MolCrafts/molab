/**
 * An attempt's scalar records as series: one per key, points in step order.
 *
 * Shared by the run view (MolPlot) and the multi-run comparison
 * (`aggregateSeries` / `multiRunMetrics`), so a run drawn alone and the same
 * run drawn beside others are built identically. Pure functions only.
 */

import { CHART_SERIES_PALETTE } from "@/lib/chart-tokens";
import type { MetricRecordSample as MetricRecord } from "@/lib/contribution-types";

/** Categorical series colours (chart freedom; not run-status tokens). */
export const PALETTE = CHART_SERIES_PALETTE;

export interface ScalarPoint {
  step: number;
  /** Epoch ms; the record's position when it carries no wall clock. */
  wall: number;
  y: number;
}

export interface ScalarSeries {
  key: string;
  group: string;
  points: ScalarPoint[];
  latest: number;
  /** Every point carries a measured wall clock (a Time axis can draw it). */
  timed?: boolean;
  /** Attempts some of these points were replayed from by the node cache. */
  replayedFrom?: string[];
}

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

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

const parseWall = (raw?: string): number => (raw ? Date.parse(raw) : Number.NaN);

interface Accumulator {
  points: ScalarPoint[];
  timed: boolean;
  replays: Set<string>;
}

const accumulate = (records: readonly MetricRecord[]): Map<string, Accumulator> => {
  const grouped = new Map<string, Accumulator>();
  records.forEach((record, index) => {
    if (record.t !== "scalar" || !isFiniteNumber(record.v)) return;
    const entry = grouped.get(record.k) ?? { points: [], timed: true, replays: new Set() };
    const source = replayedFromOf(record);
    if (source) entry.replays.add(source);
    const wall = parseWall(record.w);
    const timed = Number.isFinite(wall);
    entry.timed = entry.timed && timed;
    entry.points.push({
      step: isFiniteNumber(record.s) ? record.s : index,
      wall: timed ? wall : index,
      y: record.v,
    });
    grouped.set(record.k, entry);
  });
  return grouped;
};

/** One series per scalar key, sorted by key; other record types are ignored. */
export const buildScalarSeries = (records: readonly MetricRecord[]): ScalarSeries[] =>
  Array.from(accumulate(records).entries())
    .map(([key, { points, timed, replays }]) => {
      const sorted = [...points].sort((a, b) => a.step - b.step);
      const slash = key.indexOf("/");
      return {
        key,
        group: slash > 0 ? key.slice(0, slash) : "",
        points: sorted,
        latest: sorted[sorted.length - 1]?.y ?? 0,
        timed,
        ...(replays.size > 0 ? { replayedFrom: [...replays].sort() } : {}),
      };
    })
    .sort((left, right) => left.key.localeCompare(right.key));

/**
 * The unit each key declares (`tags.unit`), first one wins. Readers that know
 * none leave it out, and molplot never guesses one from a name.
 */
export const unitsOf = (records: readonly MetricRecord[]): ReadonlyMap<string, string> => {
  const units = new Map<string, string>();
  for (const record of records) {
    const unit = record.tags?.unit;
    if (typeof unit === "string" && unit.length > 0 && !units.has(record.k)) {
      units.set(record.k, unit);
    }
  }
  return units;
};
