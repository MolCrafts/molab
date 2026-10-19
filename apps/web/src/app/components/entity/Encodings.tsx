// ─────────────────────────────────────────────────────────────────────────────
// Visual encodings for workbench overviews.
//
// The vocabulary an Overview reaches for when the reader forms an *impression*
// rather than picks a row: magnitude in a cell, a distribution, a schedule, a
// status mix repeated across groups. Kept beside the section primitives in
// `Dashboard.tsx` so an entity surface never has to choose between a table and
// a wall of hero numbers — those are the two shapes an overview gets wrong.
//
// Colour has exactly two jobs here. Run state uses the fixed status ramp and is
// always paired with a label, never colour alone. A magnitude, including a
// duration histogram, uses the accent. It does not borrow the status ramp.
// ─────────────────────────────────────────────────────────────────────────────

import { type JSX, type ReactNode, useId } from "react";

import { STATUS_GROUPS, type StatusGroupId } from "@/app/runs/statusGroups";
import { WorkbenchAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

import type { StatusCountRollup } from "./Dashboard";
import { StatusDistribution } from "./Dashboard";
import { formatSpan } from "./gauges/scale";
import { BarInstrument } from "./InstrumentChart";

// ── MagnitudeBar ─────────────────────────────────────────────────────────────

interface MagnitudeBarProps {
  /** Measured quantity; null renders the track empty. */
  value: number | null;
  /** Domain maximum the bar is normalised against. */
  max: number;
  /** Mono readout printed beside the bar — the value is never colour-only. */
  label: ReactNode;
  title?: string;
  className?: string;
}

/**
 * One quantity inside a dense row: a hairline track plus the number.
 * Turns a column of durations into a shape the eye compares without reading.
 */
export const MagnitudeBar = ({
  value,
  max,
  label,
  title,
  className,
}: MagnitudeBarProps): JSX.Element => {
  const ratio = value !== null && max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  return (
    <span className={cn("flex min-w-0 items-center gap-2", className)} title={title}>
      <span aria-hidden className="h-1 min-w-8 flex-1 rounded-control bg-muted">
        <span
          className="block h-full rounded-control bg-accent/40"
          style={{ width: `${ratio * 100}%` }}
        />
      </span>
      <span className="shrink-0 font-mono text-label tabular-nums text-muted-foreground">
        {label}
      </span>
    </span>
  );
};

// ── Histogram ────────────────────────────────────────────────────────────────

interface HistogramProps {
  values: number[];
  /** Bucket count; clamped to the sample size. */
  bins?: number;
  /** Renders a domain value as text (axis ticks, tooltips, the summary line). */
  format: (value: number) => string;
  /** What one observation is, for the summary line ("runs", "attempts"). */
  unit: string;
  ariaLabel: string;
  className?: string;
  /** Pixel height of the columns. Omit for the shared default. */
  height?: number;
}

export interface HistogramBucket {
  from: number;
  to: number;
  count: number;
}

/**
 * Equal-width buckets over the sample's own range. Exported because bucketing
 * is the part of a histogram that can be wrong without looking wrong.
 */
export const histogramBuckets = (values: number[], bins: number): HistogramBucket[] => {
  if (values.length === 0) return [];
  const sorted = [...values].sort((left, right) => left - right);
  const min = sorted[0] ?? 0;
  const max = sorted[sorted.length - 1] ?? 0;
  const span = max - min;
  // Every observation identical: one bucket. Splitting a zero-width range into
  // `bins` buckets draws empty columns that share a key and mean nothing.
  if (span === 0) return [{ from: min, to: max, count: sorted.length }];
  const count = Math.max(1, Math.min(bins, sorted.length));
  const totals = new Array<number>(count).fill(0);
  for (const value of sorted) {
    const index = Math.min(count - 1, Math.floor(((value - min) / span) * count));
    totals[index] = (totals[index] ?? 0) + 1;
  }
  return totals.map((total, index) => ({
    from: min + (span * index) / count,
    to: min + (span * (index + 1)) / count,
    count: total,
  }));
};

const quantile = (sorted: number[], fraction: number): number => {
  if (sorted.length === 0) return 0;
  const index = (sorted.length - 1) * fraction;
  const low = Math.floor(index);
  const high = Math.ceil(index);
  const lowValue = sorted[low] ?? 0;
  if (low === high) return lowValue;
  return lowValue + ((sorted[high] ?? lowValue) - lowValue) * (index - low);
};

/**
 * Distribution of a measured quantity. A median alone changes no decision; the
 * spread does. Drawn by Vega-Lite, not a hand-built bar.
 */
export const Histogram = ({
  values,
  bins = 12,
  format,
  unit,
  ariaLabel,
  className,
  height,
}: HistogramProps): JSX.Element | null => {
  if (values.length === 0) return null;

  const sorted = [...values].sort((left, right) => left - right);
  const min = sorted[0] ?? 0;
  const max = sorted[sorted.length - 1] ?? 0;
  const median = quantile(sorted, 0.5);
  const buckets = histogramBuckets(sorted, bins);
  const mid = Math.floor((buckets.length - 1) / 2);
  const tick = (value: number): string => format(value).replace(/ /g, "\u00a0");
  const minLabel = tick(min);
  const maxLabel = tick(max);
  const medianLabel = tick(median);
  const showMedian = medianLabel !== minLabel && medianLabel !== maxLabel;

  return (
    <BarInstrument
      className={className}
      height={height}
      label={`${ariaLabel}. Median ${format(median)}, ${sorted.length} ${unit}.`}
      bars={buckets.map((bucket, index) => ({
        id: `${bucket.from}-${bucket.to}`,
        value: bucket.count,
        label:
          index === 0
            ? minLabel
            : index === buckets.length - 1 && maxLabel !== minLabel
              ? maxLabel
              : index === mid && showMedian
                ? medianLabel
                : "",
        tooltip: `${format(bucket.from)} to ${format(bucket.to)}: ${bucket.count} ${unit}`,
      }))}
    />
  );
};

// ── Schedule (attempt / run timeline) ────────────────────────────────────────

export interface ScheduleItem {
  id: string;
  label: string;
  detail?: string;
  /** Epoch ms; null when the item never started. */
  start: number | null;
  /** Epoch ms; null while still running (drawn to "now"). */
  end: number | null;
  status: StatusGroupId | null;
  /** Wraps the row when the item is openable. */
  render?: (children: ReactNode) => ReactNode;
}

const SCHEDULE_COLUMNS = "minmax(0,15rem) minmax(0,1fr) 3.5rem";

const pad2 = (value: number): string => value.toString().padStart(2, "0");

/** Clock when the window is short; month-day and clock when it spans days. */
const formatScheduleAxis = (ms: number, spanMs: number): string => {
  const date = new Date(ms);
  const clock = `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
  if (spanMs < 36 * 60 * 60 * 1000) return clock;
  return `${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${clock}`;
};

const STATUS_FILL: Record<StatusGroupId, string> = {
  running: "bg-status-running",
  pending: "bg-status-queued",
  succeeded: "bg-status-completed",
  failed: "bg-status-failed",
  cancelled: "bg-status-cancelled",
};

interface ScheduleProps {
  items: ScheduleItem[];
  /** Rendered when every item lacks a start instant. */
  empty?: ReactNode;
  className?: string;
}

/**
 * When work ran, on one shared axis. Answers "did the retry get further, and
 * was it slower?" — a question a column of timestamps makes the reader compute.
 * One line per item; the clock sits on top and a rule marks now.
 */
export const Schedule = ({ items, empty, className }: ScheduleProps): ReactNode => {
  const now = Date.now();
  const starts = items.map((item) => item.start).filter((value): value is number => value !== null);
  if (starts.length === 0) return empty ?? null;

  const min = Math.min(...starts);
  const max = Math.max(now, ...items.map((item) => item.end ?? now), min + 1);
  const span = Math.max(1, max - min);
  const ticks = [0, 1 / 3, 2 / 3].map((fraction) => min + span * fraction);
  const pct = (ms: number): string => `${(((ms - min) / span) * 100).toFixed(3)}%`;

  return (
    <div className={className}>
      <div
        aria-hidden
        className="grid items-end gap-3 px-2 pb-1 font-mono text-micro tabular-nums text-muted-foreground"
        style={{ gridTemplateColumns: SCHEDULE_COLUMNS }}
      >
        <span />
        <span className="relative block h-4">
          {ticks.map((tick) => (
            <span key={tick} className="absolute bottom-0" style={{ left: pct(tick) }}>
              {formatScheduleAxis(tick, span)}
            </span>
          ))}
          <span className="absolute right-0 bottom-0 text-foreground">now</span>
        </span>
        <span />
      </div>
      <ol className="divide-y divide-border/50 border-t border-border">
        {items.map((item) => {
          const start = item.start;
          const end = item.end ?? now;
          const left = start === null ? 0 : ((start - min) / span) * 100;
          const width = start === null ? 0 : Math.max(0.8, ((end - start) / span) * 100);
          const fill = item.status ? STATUS_FILL[item.status] : "bg-muted-foreground/40";
          const duration = start === null ? "" : formatSpan(Math.max(0, end - start) / 1000);
          const statusWord = STATUS_GROUPS.find((group) => group.id === item.status)?.label ?? null;
          const title = [item.label, item.detail, statusWord, duration]
            .filter((part) => part != null && part !== "")
            .join(" · ");
          const row = (
            <span
              className="grid min-w-0 items-center gap-3 px-2 py-2"
              style={{ gridTemplateColumns: SCHEDULE_COLUMNS }}
              title={title}
            >
              <span className="min-w-0 truncate text-body text-foreground">{item.label}</span>
              <span className="relative h-3">
                {ticks.slice(1).map((tick) => (
                  <span
                    key={tick}
                    aria-hidden
                    className="absolute inset-y-0 w-px bg-border/60"
                    style={{ left: pct(tick) }}
                  />
                ))}
                <span aria-hidden className="absolute inset-y-0 right-0 w-px bg-foreground/40" />
                {start !== null ? (
                  <span
                    className={cn(
                      "absolute top-1/2 h-2 -translate-y-1/2 rounded-hairline",
                      fill,
                      item.end === null && "mol-motion-progress-pulse",
                    )}
                    style={{ left: `${left}%`, width: `${Math.min(100 - left, width)}%` }}
                  />
                ) : (
                  <span className="absolute inset-y-0 left-0 flex items-center text-micro text-muted-foreground">
                    {statusWord ?? "not started"}
                  </span>
                )}
              </span>
              <span className="text-right font-mono text-label tabular-nums text-muted-foreground">
                {duration}
              </span>
            </span>
          );
          return (
            <li key={item.id} className="min-w-0">
              {item.render ? item.render(row) : row}
            </li>
          );
        })}
      </ol>
    </div>
  );
};

// ── StatusLegend + StatusBreakdown ───────────────────────────────────────────

/** One legend for a whole page of small multiples, so no bar is colour-alone. */
export const StatusLegend = ({ className }: { className?: string }): JSX.Element => (
  <ul className={cn("flex flex-wrap items-center gap-x-4 gap-y-1", className)}>
    {STATUS_GROUPS.map((group) => (
      <li key={group.id} className="flex items-center gap-2 text-label text-muted-foreground">
        <span
          aria-hidden
          className="size-1.5 rounded-full"
          style={{ backgroundColor: group.color }}
        />
        {group.label}
      </li>
    ))}
  </ul>
);

export interface BreakdownGroup {
  id: string;
  label: string;
  /** Quiet second line — an axis value's run count, a backend's cluster. */
  detail?: ReactNode;
  counts: StatusCountRollup;
  onSelect?: () => void;
}

interface StatusBreakdownProps {
  groups: BreakdownGroup[];
  /** Column label above the group names. */
  caption?: string;
  className?: string;
}

/**
 * The same status mix, repeated across groups — experiments in a project,
 * values of a swept parameter, backends in a workspace. Small multiples, so the
 * outlier is found by shape instead of by reading every row's numbers.
 */
export const StatusBreakdown = ({
  groups,
  caption,
  className,
}: StatusBreakdownProps): JSX.Element => {
  const captionId = useId();
  return (
    <div className={cn("space-y-2", className)}>
      {caption != null && (
        <p id={captionId} className="text-label text-muted-foreground">
          {caption}
        </p>
      )}
      <ul aria-labelledby={caption != null ? captionId : undefined} className="space-y-2">
        {groups.map((group) => {
          const body = (
            <>
              <span className="min-w-0">
                <span className="block truncate text-label text-foreground">{group.label}</span>
                {group.detail != null && (
                  <span className="block truncate text-micro text-muted-foreground">
                    {group.detail}
                  </span>
                )}
              </span>
              <StatusDistribution counts={group.counts} variant="meter" className="justify-end" />
              <span className="text-right font-mono text-label tabular-nums text-foreground">
                {group.counts.total}
              </span>
              <span
                className={cn(
                  "text-right font-mono text-label tabular-nums",
                  group.counts.failed > 0
                    ? "text-status-failed-foreground"
                    : "text-muted-foreground",
                )}
              >
                {group.counts.failed > 0
                  ? `${Math.round((group.counts.failed / group.counts.total) * 100)}% failed`
                  : "none failed"}
              </span>
            </>
          );
          const layout =
            "grid grid-cols-[fit-content(10rem)_minmax(6rem,1fr)_2rem_5.5rem] items-center gap-3";
          return (
            <li key={group.id} className="min-w-0">
              {group.onSelect ? (
                <WorkbenchAction
                  kind="ghost"
                  size="content"
                  onClick={group.onSelect}
                  className={cn(layout, "w-full rounded-control py-1 text-left")}
                >
                  {body}
                </WorkbenchAction>
              ) : (
                <span className={cn(layout, "py-1")}>{body}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
};
