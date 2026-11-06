// ─────────────────────────────────────────────────────────────────────────────
// Full-width overview charts. Each takes plain points (no run rows), turns them
// into its named dataset, and reports picks and brushes as callbacks.
// ─────────────────────────────────────────────────────────────────────────────

import { type JSX, useMemo } from "react";

import { STATUS_GROUPS, type StatusGroupId } from "@/app/runs/statusGroups";

import type { BreakdownGroup } from "../../Encodings";
import { useStatusColors } from "../../InstrumentChart";
import type { DurationSeries } from "../DurationStrip";
import { formatSpan, spanScale, stackLanes, type TimeBucket } from "../scale";
import {
  ACTIVITY_HEIGHT,
  activitySpec,
  BAR_ROW,
  barsSpec,
  DURATION_ROW,
  durationSpec,
  MIX_ROW,
  mixSpec,
  POSITION_HEIGHT,
  positionSpec,
  TIMELINE_ROW,
  timelineSpec,
} from "./chartSpecs";
import { OverviewChart } from "./OverviewChart";

type Colors = Record<StatusGroupId, string> | null;

const paint = (colors: Colors, status: StatusGroupId | null): string =>
  status && colors ? colors[status] : "transparent";

const pad2 = (value: number): string => value.toString().padStart(2, "0");
const clock = (ms: number): string => {
  const date = new Date(ms);
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
};

// ── Activity ─────────────────────────────────────────────────────────────────

const OUTCOMES = [
  { key: "succeeded", label: "succeeded", status: "succeeded" },
  { key: "failed", label: "failed", status: "failed" },
  { key: "cancelled", label: "cancelled", status: "cancelled" },
  { key: "other", label: "other", status: null },
] as const;

export const activityRows = (buckets: readonly TimeBucket[], colors: Colors) =>
  buckets.flatMap((bucket) => {
    const key = String(bucket.start);
    const span = `${clock(bucket.start)}–${clock(bucket.end)}`;
    const finished = OUTCOMES.reduce((sum, outcome) => sum + bucket.finishes[outcome.key], 0);
    // A hairline between columns, so neighbouring buckets never merge.
    const end = bucket.end - (bucket.end - bucket.start) * 0.14;
    // Stacked here, not by Vega: starts rise from zero, outcomes hang below it in order.
    const rows: Record<string, unknown>[] = [];
    if (bucket.starts > 0) {
      rows.push({
        key,
        kind: "started",
        start: bucket.start,
        end,
        y0: 0,
        y1: bucket.starts,
        color: null,
        tip: `${span} · ${bucket.starts} started`,
      });
    }
    let below = 0;
    for (const outcome of OUTCOMES) {
      const count = bucket.finishes[outcome.key];
      if (count === 0) continue;
      rows.push({
        key,
        kind: outcome.key,
        start: bucket.start,
        end,
        y0: -below,
        y1: -(below + count),
        color: paint(colors, outcome.status),
        tip: `${span} · ${count} ${outcome.label} of ${finished} finished`,
      });
      below += count;
    }
    return rows;
  });

export const ActivityChart = ({
  buckets,
  window,
  onBrush,
}: {
  buckets: readonly TimeBucket[];
  window: { from: number; to: number };
  onBrush?: (window: [number, number] | null) => void;
}): JSX.Element => {
  const colors = useStatusColors();
  const data = useMemo(() => ({ activity: activityRows(buckets, colors) }), [buckets, colors]);
  return (
    <OverviewChart
      label="Executions started and finished over time"
      spec={(palette) => activitySpec(palette, window)}
      specKey={`activity:${window.from}:${window.to}`}
      data={data}
      height={ACTIVITY_HEIGHT}
      brushField="start"
      onBrush={onBrush}
    />
  );
};

// ── Status mix ───────────────────────────────────────────────────────────────

const ORDER: readonly StatusGroupId[] = ["running", "pending", "succeeded", "failed", "cancelled"];

export const mixRows = (
  groups: readonly BreakdownGroup[],
  colors: Colors,
  selected: string | null = null,
) =>
  groups.flatMap((group, gorder) => {
    const { total, failed } = group.counts;
    const share = total === 0 ? 0 : Math.round((failed / total) * 100);
    return ORDER.map((status, sorder) => {
      const label = STATUS_GROUPS.find((item) => item.id === status)?.label ?? status;
      const count = group.counts[status];
      return {
        key: group.id,
        group: group.label,
        gorder,
        status,
        sorder,
        count,
        color: paint(colors, status),
        outline: status === "pending",
        tip: `${group.label} · ${label}: ${count} of ${total} executions${
          failed > 0 ? `\n${share}% failed` : ""
        }`,
        // The failed share prints in failed ink; the word would only repeat the colour.
        summary: failed > 0 ? `${total} · ${share}%` : `${total}`,
        alarm: failed > 0,
        faded: selected !== null && group.id !== selected,
      };
    });
  });

export const MixChart = ({
  groups,
  label,
  selected = null,
  onPick,
}: {
  groups: readonly BreakdownGroup[];
  label: string;
  /** The group a filter holds; the others stay receded. */
  selected?: string | null;
  onPick?: (id: string) => void;
}): JSX.Element => {
  const colors = useStatusColors();
  const data = useMemo(
    () => ({ mix: mixRows(groups, colors, selected) }),
    [groups, colors, selected],
  );
  return (
    <OverviewChart
      label={label}
      spec={(palette) => mixSpec(palette, groups.length)}
      specKey={`mix:${groups.length}`}
      data={data}
      height={Math.max(1, groups.length) * MIX_ROW}
      onPick={onPick}
    />
  );
};

// ── Durations ────────────────────────────────────────────────────────────────

export const durationRows = (series: readonly DurationSeries[], colors: Colors) => {
  const all = series.flatMap((item) => item.points.map((point) => point.seconds));
  const scale = spanScale(all);
  const rows = series.flatMap((item, gorder) => {
    const lanes = stackLanes(
      item.points.map((point) => scale.at(point.seconds)),
      0.014,
    );
    return item.points.map((point, index) => ({
      key: point.id,
      group: typeof item.label === "string" ? item.label : item.id,
      gorder,
      seconds: point.seconds,
      // Lanes alternate around the row's centre line, a tenth of a row apart (±4 lanes stay inside it).
      row: gorder + (lanes[index] ?? 0) * 0.1,
      color: point.status && colors ? colors[point.status] : "transparent",
      tip: `${point.label} · ${formatSpan(point.seconds)}`,
    }));
  });
  const groups = series.map((item) => (typeof item.label === "string" ? item.label : item.id));
  return { rows, groups, axis: { domain: scale.domain, ticks: scale.ticks, log: scale.log } };
};

export const DurationDots = ({
  series,
  onPick,
}: {
  series: readonly DurationSeries[];
  onPick?: (key: string) => void;
}): JSX.Element => {
  const colors = useStatusColors();
  const { rows, groups, axis } = useMemo(() => durationRows(series, colors), [series, colors]);
  const data = useMemo(() => ({ durations: rows }), [rows]);
  return (
    <OverviewChart
      label="Duration of every finished run, by group"
      spec={(palette) => durationSpec(palette, axis, groups)}
      specKey={`durations:${groups.join("|")}:${axis.domain.join(",")}:${axis.log}`}
      data={data}
      height={Math.max(1, series.length) * DURATION_ROW}
      onPick={onPick}
    />
  );
};

// ── Timeline ─────────────────────────────────────────────────────────────────

export interface TimelineSpan {
  key: string;
  label: string;
  start: number;
  /** Null while running: drawn to now. */
  end: number | null;
  status: StatusGroupId | null;
  tip: string;
}

/** Labels must be distinct for the band scale; repeats get an invisible suffix. */
const distinct = (labels: readonly string[]): string[] => {
  const seen = new Map<string, number>();
  return labels.map((label) => {
    const count = seen.get(label) ?? 0;
    seen.set(label, count + 1);
    return count === 0 ? label : `${label}${"​".repeat(count)}`;
  });
};

export const TimelineChart = ({
  spans,
  label = "When each run ran",
  onPick,
}: {
  spans: readonly TimelineSpan[];
  label?: string;
  onPick?: (key: string) => void;
}): JSX.Element => {
  const colors = useStatusColors();
  const now = useMemo(() => Date.now(), []);
  const from = spans.length > 0 ? Math.min(...spans.map((span) => span.start)) : now - 3_600_000;
  // A finished set ends at its last finish; only live work stretches the clock to now.
  const live = spans.some((span) => span.end === null);
  const last = Math.max(from + 1, ...spans.map((span) => span.end ?? now));
  const window = { from, to: live ? Math.max(now, last) : last };
  const data = useMemo(() => {
    const labels = distinct(spans.map((span) => span.label));
    return {
      spans: spans.map((span, order) => ({
        key: span.key,
        label: labels[order],
        order,
        start: span.start,
        end: Math.max(span.end ?? now, span.start + 1),
        color: paint(colors, span.status),
        tip: span.tip,
      })),
    };
  }, [spans, colors, now]);
  return (
    <OverviewChart
      label={label}
      spec={(palette) => timelineSpec(palette, spans.length, window, live)}
      specKey={`timeline:${spans.length}:${window.from}:${window.to}:${live}`}
      data={data}
      height={Math.max(1, spans.length) * TIMELINE_ROW + 28}
      onPick={onPick}
    />
  );
};

// ── Counts per category ──────────────────────────────────────────────────────

export interface CountBar {
  key: string;
  label: string;
  value: number;
  /** Printed past a horizontal bar: "3 tasks". */
  readout: string;
  tip: string;
}

/** Tick text for the vertical magnitude axis, as a Vega expression over `datum.value`. */
export const BYTES_EXPR =
  "datum.value >= 1073741824 ? format(datum.value / 1073741824, '.1f') + ' GB' : " +
  "datum.value >= 1048576 ? format(datum.value / 1048576, '.1f') + ' MB' : " +
  "datum.value >= 1024 ? format(datum.value / 1024, '.0f') + ' KB' : format(datum.value, 'd') + ' B'";

export const CountBars = ({
  bars,
  label,
  orientation = "horizontal",
  valueExpr = "format(datum.value, 'd')",
  onPick,
}: {
  bars: readonly CountBar[];
  label: string;
  orientation?: "vertical" | "horizontal";
  /** Vertical axis tick text, a Vega expression over `datum.value`. */
  valueExpr?: string;
  onPick?: (key: string) => void;
}): JSX.Element => {
  const data = useMemo(() => ({ bars: bars.map((bar, order) => ({ ...bar, order })) }), [bars]);
  const horizontal = orientation === "horizontal";
  return (
    <OverviewChart
      label={label}
      spec={(palette) => barsSpec(palette, orientation, bars.length, valueExpr)}
      specKey={`bars:${orientation}:${bars.length}:${valueExpr}`}
      data={data}
      height={horizontal ? Math.max(1, bars.length) * BAR_ROW : 180}
      onPick={onPick}
    />
  );
};

// ── One run among its siblings ───────────────────────────────────────────────

export interface SiblingPoint {
  key: string;
  seconds: number;
  status: StatusGroupId | null;
  /** The run on the page. */
  self: boolean;
  tip: string;
}

export const PositionChart = ({
  points,
  onPick,
}: {
  points: readonly SiblingPoint[];
  onPick?: (key: string) => void;
}): JSX.Element => {
  const colors = useStatusColors();
  const { rows, axis } = useMemo(() => {
    const scale = spanScale(points.map((point) => point.seconds));
    const others = points.filter((point) => !point.self);
    const lanes = stackLanes(
      others.map((point) => scale.at(point.seconds)),
      0.02,
    );
    const laneOf = new Map(others.map((point, index) => [point.key, lanes[index] ?? 0]));
    return {
      rows: points.map((point) => ({
        key: point.key,
        seconds: point.seconds,
        self: point.self,
        // Siblings sit on lanes around the line; the run itself stays on it.
        lane: point.self ? 0 : (laneOf.get(point.key) ?? 0) || 1,
        color: point.status && colors ? colors[point.status] : "transparent",
        tip: point.tip,
      })),
      axis: { domain: scale.domain, ticks: scale.ticks, log: scale.log },
    };
  }, [points, colors]);
  const data = useMemo(() => ({ siblings: rows }), [rows]);
  return (
    <OverviewChart
      label="This run's duration among the experiment's finished runs"
      spec={(palette) => positionSpec(palette, axis)}
      specKey={`position:${axis.domain.join(",")}:${axis.log}`}
      data={data}
      height={POSITION_HEIGHT}
      onPick={(key) => {
        if (!points.find((point) => point.key === key)?.self) onPick?.(key);
      }}
    />
  );
};
