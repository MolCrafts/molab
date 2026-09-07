/**
 * Turning molrs's parsers into the records a chart consumes.
 *
 * This is the *mapping*, kept apart from registration so it can be tested
 * without a plugin runtime. molrs owns the parsing; what lives here is the
 * decision about which column becomes which series, and how the viewer's
 * sampling policy is applied.
 */

import type { MetricReadRequest, MetricRecordSample } from "@/lib/contribution-types";
import type { ThermoTable } from "@/lib/molrs";

const STEP_COLUMN = "Step";

/**
 * Decides which samples survive the viewer's requested step resolution.
 *
 * Per series, because series are emitted interleaved and each must be thinned
 * on its own timeline. A sample with no step is always kept — it is a one-off
 * scalar, not a point on a curve.
 */
class StepGate {
  private readonly lastKept = new Map<string, number>();

  constructor(private readonly interval: number | undefined) {}

  keeps(key: string, step: number | undefined): boolean {
    if (!this.interval || this.interval <= 0 || step === undefined) {
      return true;
    }
    const previous = this.lastKept.get(key);
    if (previous !== undefined && step - previous < this.interval) {
      return false;
    }
    this.lastKept.set(key, step);
    return true;
  }
}

/**
 * Map LAMMPS thermo tables to metric records.
 *
 * One record per (row, non-step column): `Step` becomes each record's `s`,
 * never a series of its own. **Thermo rows carry no wall clock** — LAMMPS
 * records simulation steps, so no `w` is emitted; synthesizing one from
 * `Loop time` would be fabricated data.
 *
 * A row is one sample of every column at once, so the stride is applied to
 * *rows*. Striding the flattened records would land on the same column every
 * time and drop the other curves entirely.
 */
export const thermoRecords = (
  tables: ThermoTable[],
  request: MetricReadRequest,
  source: string,
): MetricRecordSample[] => {
  const wanted = request.keys && request.keys.length > 0 ? new Set(request.keys) : null;
  const records: MetricRecordSample[] = [];
  const gate = new StepGate(request.stepInterval);

  for (const table of tables) {
    const stepAt = table.columns.indexOf(STEP_COLUMN);
    for (const row of table.rows) {
      const step = stepAt >= 0 ? row[stepAt] : undefined;
      for (let position = 0; position < table.columns.length; position += 1) {
        if (position === stepAt) continue;
        const key = `lammps/${table.columns[position]}`;
        if (wanted && !wanted.has(key)) continue;
        if (!gate.keeps(key, step)) continue;
        records.push({
          t: "scalar",
          k: key,
          ...(step === undefined ? {} : { s: step }),
          v: row[position],
          tags: { run_index: table.runIndex, wall_time_source: "read", source },
        });
        if (request.limit !== undefined && records.length >= request.limit) {
          return records;
        }
      }
    }
  }
  return records;
};

/**
 * Read molexp's own metrics WAL.
 *
 * It is already in record form, so there is nothing to map — but it gets no
 * special treatment for that: it arrives through the same contribution as
 * every other format.
 *
 * Series interleave line by line, so the stride is counted **per series**;
 * striding the file would keep one key and drop the rest.
 */
export const walRecords = (
  text: string,
  request: MetricReadRequest,
  source: string,
): MetricRecordSample[] => {
  const wanted = request.keys && request.keys.length > 0 ? new Set(request.keys) : null;
  const gate = new StepGate(request.stepInterval);
  const records: MetricRecordSample[] = [];

  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    let record: MetricRecordSample;
    try {
      record = JSON.parse(trimmed) as MetricRecordSample;
    } catch {
      continue; // a torn last line of a live WAL is normal, not an error
    }
    if (typeof record?.k !== "string") continue;
    if (wanted && !wanted.has(record.k)) continue;
    if (!gate.keeps(record.k, typeof record.s === "number" ? record.s : undefined)) continue;
    record.tags = { source, ...(record.tags ?? {}) };
    records.push(record);
    if (request.limit !== undefined && records.length >= request.limit) break;
  }
  return records;
};
