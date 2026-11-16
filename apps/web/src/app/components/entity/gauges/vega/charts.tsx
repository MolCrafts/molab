// ─────────────────────────────────────────────────────────────────────────────
// Full-width overview charts. Each takes plain points (no run rows), turns them
// into its named dataset, and reports picks and brushes as callbacks.
// ─────────────────────────────────────────────────────────────────────────────

import { type JSX, type ReactNode, useMemo } from "react";

import { CHART_GROUPS, type ChartGroupId } from "@/app/status/vocabulary";

import type { BreakdownGroup } from "../../Encodings";
import { useStatusColors } from "../../InstrumentChart";
import { formatSpan, spanScale, stackLanes, type TimeBucket } from "../scale";
import {
  ACTIVITY_HEIGHT,
  activitySpec,
  BAR_ROW,
  barsSpec,
  CLOCK_AXIS,
  CLOCK_ROW,
  COMPARE_ROW,
  compareBarsSpec,
  DURATION_ROW,
  durationSpec,
  MIX_ROW,
  mixSpec,
  STATUS_BAR_HEIGHT,
  SWEEP_HEIGHT,
  statusBarSpec,
  sweepSpec,
  taskClockSpec,
} from "./chartSpecs";
import { OverviewChart } from "./OverviewChart";

type Colors = Record<ChartGroupId, string> | null;

const paint = (colors: Colors, status: ChartGroupId | null): string =>
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

/** What a mix counts, and its own word for a status where the status word would mislead. */
export interface MixWording {
  /** Singular, plural: "run", "runs". */
  unit?: readonly [string, string];
  words?: Partial<Record<ChartGroupId, string>>;
}

export const mixRows = (
  groups: readonly BreakdownGroup[],
  colors: Colors,
  selected: string | null = null,
  { unit = ["execution", "executions"], words = {} }: MixWording = {},
) =>
  groups.flatMap((group, gorder) => {
    const { total, failed } = group.counts;
    const share = total === 0 ? 0 : Math.round((failed / total) * 100);
    return CHART_GROUPS.map(({ id: status, outline, label: statusLabel }, sorder) => {
      const label = words[status] ?? statusLabel;
      const count = group.counts[status];
      return {
        key: group.id,
        group: group.label,
        gorder,
        status,
        sorder,
        count,
        color: paint(colors, status),
        outline,
        tip: `${group.label} · ${label}: ${count} of ${total} ${total === 1 ? unit[0] : unit[1]}${
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
  wording,
}: {
  groups: readonly BreakdownGroup[];
  label: string;
  /** The group a filter holds; the others stay receded. */
  selected?: string | null;
  onPick?: (id: string) => void;
  /** Tooltip unit and status words (default: executions, status words). */
  wording?: MixWording;
}): JSX.Element => {
  const colors = useStatusColors();
  const data = useMemo(
    () => ({ mix: mixRows(groups, colors, selected, wording) }),
    [groups, colors, selected, wording],
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

/** One group's composition as a single bar (Preview width). */
export const StatusBar = ({
  group,
  label,
}: {
  group: BreakdownGroup;
  label: string;
}): JSX.Element => {
  const colors = useStatusColors();
  const data = useMemo(
    () => ({ mix: mixRows([group], colors).filter((row) => row.count > 0) }),
    [group, colors],
  );
  return (
    <OverviewChart
      label={label}
      spec={statusBarSpec}
      specKey="status-bar"
      data={data}
      height={STATUS_BAR_HEIGHT}
      empty={group.counts.total === 0}
    />
  );
};

// ── Durations ────────────────────────────────────────────────────────────────

/** One finished run on a duration axis. */
export interface DurationPoint {
  id: string;
  seconds: number;
  status: ChartGroupId | null;
  label: string;
  href?: string;
}

export interface DurationSeries {
  id: string;
  label?: ReactNode;
  points: DurationPoint[];
}

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

// ── Tasks on a clock ─────────────────────────────────────────────────────────

export interface ClockTask {
  key: string;
  start: number | null;
  /** Null while it runs, or when it never started. */
  end: number | null;
  status: ChartGroupId | null;
  /** Drawn in place of a bar when the task never started. */
  note: string | null;
  tip: string;
}

/** The status that earns an end mark: an ending that is not a success. */
const ENDING_MARKS: ReadonlySet<ChartGroupId> = new Set(["failed", "interrupted", "cancelled"]);

export const TaskClockChart = ({
  tasks,
  label,
  onPick,
}: {
  tasks: readonly ClockTask[];
  label: string;
  onPick?: (key: string) => void;
}): JSX.Element => {
  const colors = useStatusColors();
  const now = useMemo(() => Date.now(), []);
  const starts = tasks.flatMap((task) => (task.start === null ? [] : [task.start]));
  const from = starts.length > 0 ? Math.min(...starts) : now - 60_000;
  const live = tasks.some((task) => task.start !== null && task.end === null);
  const last = Math.max(
    from + 1,
    ...tasks.map((task) => task.end ?? (task.start === null ? from : now)),
  );
  const window = { from, to: live ? Math.max(now, last) : last };
  const data = useMemo(() => {
    let anchor = from;
    return {
      tasks: tasks.map((task, order) => {
        const bar = task.start !== null;
        const end = bar ? Math.max(task.end ?? now, (task.start ?? 0) + 1) : null;
        const row = {
          key: task.key,
          order,
          bar,
          live: bar && task.end === null,
          start: task.start,
          end,
          anchor,
          note: task.note ?? "",
          mark:
            bar && task.end !== null && task.status && ENDING_MARKS.has(task.status)
              ? paint(colors, task.status)
              : null,
          tip: task.tip,
        };
        if (end !== null) anchor = end;
        return row;
      }),
    };
  }, [tasks, colors, now, from]);
  return (
    <OverviewChart
      label={label}
      spec={(palette) => taskClockSpec(palette, tasks.length, window)}
      specKey={`clock:${tasks.length}:${window.from}:${window.to}`}
      data={data}
      height={Math.max(1, tasks.length) * CLOCK_ROW + CLOCK_AXIS}
      onPick={onPick}
    />
  );
};

// ── One run among its siblings, on the swept axis ────────────────────────────

export interface SweepChartPoint {
  key: string;
  x: string;
  xOrder: number;
  y: number | null;
  series: string;
  self: boolean;
  status: ChartGroupId | null;
  tip: string;
}

export const SweepChart = ({
  points,
  selfSeries,
  label,
  onPick,
}: {
  points: readonly SweepChartPoint[];
  /** The line the run on the page belongs to; null draws every line in the accent. */
  selfSeries: string | null;
  label: string;
  onPick?: (key: string) => void;
}): JSX.Element => {
  const colors = useStatusColors();
  const { rows, axis } = useMemo(() => {
    const labels = [...points]
      .sort((left, right) => left.xOrder - right.xOrder)
      .map((point) => point.x)
      .filter((value, index, all) => all.indexOf(value) === index);
    const ys = points.flatMap((point) => (point.y === null ? [] : [point.y]));
    const low = Math.min(...ys);
    const high = Math.max(...ys);
    const log = low > 0 && high / low > 30;
    const domain: [number, number] = log
      ? [low / 1.6, high * 1.6]
      : [
          low - (high - low || Math.abs(low) || 1) * 0.1,
          high + (high - low || Math.abs(high) || 1) * 0.1,
        ];
    // Each line is named once, at its last point; lines that end on the same
    // point share one label ("ase · nve / ase · nvt") instead of overprinting.
    const lastOf = new Map<string, SweepChartPoint>();
    for (const point of points) {
      if (point.y === null) continue;
      const current = lastOf.get(point.series);
      if (!current || point.xOrder >= current.xOrder) lastOf.set(point.series, point);
    }
    const labelAt = new Map<string, { key: string; names: string[] }>();
    for (const [series, point] of lastOf) {
      const spot = `${point.xOrder}:${point.y?.toPrecision(3)}`;
      const entry = labelAt.get(spot);
      if (entry) entry.names.push(series);
      else labelAt.set(spot, { key: point.key, names: [series] });
    }
    const labelOf = new Map(
      [...labelAt.values()].map((entry) => [entry.key, entry.names.sort().join(" / ")]),
    );
    return {
      axis: { labels, log, domain, small: Math.max(Math.abs(low), Math.abs(high)) < 1e-2 },
      rows: points.map((point) => ({
        key: point.key,
        x: point.x,
        xOrder: labels.indexOf(point.x),
        y: point.y,
        plotY: point.y ?? domain[1],
        series: point.series,
        self: point.self,
        own: selfSeries === null || point.series === selfSeries,
        color: paint(colors, point.status),
        label:
          point.self && point.y === null
            ? point.tip.replace(/^This run/, "this run")
            : (labelOf.get(point.key) ?? null),
        tip: point.tip,
      })),
    };
  }, [points, selfSeries, colors]);
  const data = useMemo(() => ({ points: rows }), [rows]);
  return (
    <OverviewChart
      label={label}
      spec={(palette) => sweepSpec(palette, axis)}
      specKey={`sweep:${axis.labels.join(",")}:${axis.log}:${axis.domain.join(",")}`}
      data={data}
      height={SWEEP_HEIGHT + 24}
      onPick={(key) => {
        if (!points.find((point) => point.key === key)?.self) onPick?.(key);
      }}
    />
  );
};

// ── One result across compared runs ─────────────────────────────────────────

export interface CompareBar {
  key: string;
  label: string;
  value: number | null;
  /** Printed past the bar, or in place of it when there is no value. */
  printed: string;
  status: ChartGroupId | null;
  tip: string;
}

export const CompareBarsChart = ({
  bars,
  baseline,
  label,
  onPick,
}: {
  bars: readonly CompareBar[];
  /** The baseline run's value: a dashed rule. */
  baseline: number | null;
  label: string;
  onPick?: (key: string) => void;
}): JSX.Element => {
  const colors = useStatusColors();
  const axis = useMemo(() => {
    const values = bars.flatMap((bar) => (bar.value === null ? [] : [bar.value]));
    const low = values.length ? Math.min(...values) : 0;
    const high = values.length ? Math.max(...values) : 1;
    const log = low > 0 && high / low > 30;
    const domain: [number, number] = log
      ? [low / 2, high * 2]
      : [Math.min(0, low), high === 0 ? 1 : high * 1.1];
    return { domain, log, baseline };
  }, [bars, baseline]);
  const data = useMemo(
    () => ({
      bars: bars.map((bar, order) => ({
        ...bar,
        order,
        color: paint(colors, bar.status),
      })),
    }),
    [bars, colors],
  );
  return (
    <OverviewChart
      label={label}
      spec={(palette) => compareBarsSpec(palette, bars.length, axis)}
      specKey={`compare:${bars.length}:${axis.domain.join(",")}:${axis.log}:${axis.baseline}`}
      data={data}
      height={Math.max(1, bars.length) * COMPARE_ROW + 28}
      onPick={onPick}
    />
  );
};
