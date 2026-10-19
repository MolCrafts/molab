// ─────────────────────────────────────────────────────────────────────────────
// Scale arithmetic for the overview gauges. Pure functions, no React: the part
// of a chart that can be wrong without looking wrong lives here, under test.
// ─────────────────────────────────────────────────────────────────────────────

import type { StatusGroupId } from "@/app/runs/statusGroups";

/** Seconds per unit — the candidate tick steps a duration axis may land on. */
const DURATION_STEPS = [
  1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800,
  604800,
] as const;

/** A duration a person reads at a glance: "2.4s", "48m", "1h 28m", "3d 4h". */
export const formatSpan = (seconds: number): string => {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 10) return `${Number(seconds.toFixed(1))}s`;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  if (hours < 24) return restMinutes === 0 ? `${hours}h` : `${hours}h ${restMinutes}m`;
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours === 0 ? `${days}d` : `${days}d ${restHours}h`;
};

export const quantile = (sorted: readonly number[], fraction: number): number => {
  if (sorted.length === 0) return 0;
  const index = (sorted.length - 1) * fraction;
  const low = Math.floor(index);
  const high = Math.ceil(index);
  const lowValue = sorted[low] ?? 0;
  if (low === high) return lowValue;
  return lowValue + ((sorted[high] ?? lowValue) - lowValue) * (index - low);
};

export interface SpanScale {
  /** Position of a value along the axis, 0..1. */
  at: (value: number) => number;
  ticks: number[];
  log: boolean;
}

/**
 * Axis for a set of durations. A spread wider than 20× goes logarithmic, so a
 * 4-second smoke test and a 6-hour production run both stay legible on one line.
 */
export const spanScale = (values: readonly number[]): SpanScale => {
  const finite = values.filter((value) => Number.isFinite(value) && value >= 0);
  const rawMin = finite.length > 0 ? Math.min(...finite) : 0;
  const rawMax = finite.length > 0 ? Math.max(...finite) : 1;
  const log = rawMin > 0 && rawMax / rawMin > 20;

  if (log) {
    const lo = Math.log10(rawMin) - 0.08;
    const hi = Math.log10(rawMax) + 0.08;
    const at = (value: number): number =>
      Math.min(1, Math.max(0, (Math.log10(Math.max(value, 1e-3)) - lo) / (hi - lo)));
    const inside = DURATION_STEPS.filter((step) => step >= 10 ** lo && step <= 10 ** hi);
    const stride = Math.max(1, Math.ceil(inside.length / 5));
    const ticks = inside.filter((_, index) => index % stride === 0);
    return { at, ticks: ticks.length >= 2 ? ticks : [rawMin, rawMax], log };
  }

  // Linear: pad the domain so a single value or a tight cluster sits mid-axis
  // instead of pinned to an edge.
  const spread = rawMax - rawMin;
  const pad = spread === 0 ? Math.max(rawMax * 0.5, 30) : spread * 0.12;
  const lo = Math.max(0, rawMin - pad);
  const hi = rawMax + pad;
  const step =
    DURATION_STEPS.find((candidate) => (hi - lo) / candidate <= 5) ??
    DURATION_STEPS[DURATION_STEPS.length - 1];
  const ticks: number[] = [];
  for (let tick = Math.ceil(lo / step) * step; tick <= hi; tick += step) ticks.push(tick);
  const at = (value: number): number => Math.min(1, Math.max(0, (value - lo) / (hi - lo)));
  return { at, ticks, log };
};

/**
 * Lane for each dot so that dots closer than `gap` (in axis fraction) stack
 * instead of hiding each other. Lanes alternate around the track: 0, 1, -1, 2…
 */
export const stackLanes = (positions: readonly number[], gap = 0.018): number[] => {
  const order = positions.map((position, index) => ({ position, index }));
  order.sort((left, right) => left.position - right.position);
  const lanes = new Array<number>(positions.length).fill(0);
  const placed: { position: number; lane: number }[] = [];
  const LANE_ORDER = [0, -1, 1, -2, 2, -3, 3, -4, 4];
  for (const { position, index } of order) {
    const busy = new Set(
      placed.filter((dot) => Math.abs(dot.position - position) < gap).map((dot) => dot.lane),
    );
    const lane = LANE_ORDER.find((candidate) => !busy.has(candidate)) ?? 0;
    lanes[index] = lane;
    placed.push({ position, lane });
  }
  return lanes;
};

export interface StatusCounts {
  total: number;
  running: number;
  pending: number;
  succeeded: number;
  failed: number;
  cancelled: number;
}

/** Share of finished work that succeeded. `null` until something has finished. */
export const successShare = (counts: StatusCounts): number | null => {
  const finished = counts.succeeded + counts.failed + counts.cancelled;
  return finished === 0 ? null : counts.succeeded / finished;
};

export interface TimeBucket {
  start: number;
  end: number;
  starts: number;
  finishes: Record<"succeeded" | "failed" | "cancelled" | "other", number>;
}

export interface TimedEvent {
  startedAt: number | null;
  finishedAt: number | null;
  outcome: StatusGroupId | null;
}

/** Equal time buckets ending at `now`; starts and finishes counted separately. */
export const timeBuckets = (
  events: readonly TimedEvent[],
  now: number,
  windowMs: number,
  count: number,
): TimeBucket[] => {
  const width = windowMs / count;
  const origin = now - windowMs;
  const buckets: TimeBucket[] = Array.from({ length: count }, (_, index) => ({
    start: origin + index * width,
    end: origin + (index + 1) * width,
    starts: 0,
    finishes: { succeeded: 0, failed: 0, cancelled: 0, other: 0 },
  }));
  const slot = (at: number): TimeBucket | undefined =>
    at < origin || at > now
      ? undefined
      : buckets[Math.min(count - 1, Math.floor((at - origin) / width))];
  for (const event of events) {
    if (event.startedAt !== null) {
      const bucket = slot(event.startedAt);
      if (bucket) bucket.starts += 1;
    }
    if (event.finishedAt !== null) {
      const bucket = slot(event.finishedAt);
      if (!bucket) continue;
      const outcome = event.outcome;
      const key =
        outcome === "succeeded" || outcome === "failed" || outcome === "cancelled"
          ? outcome
          : "other";
      bucket.finishes[key] += 1;
    }
  }
  return buckets;
};
