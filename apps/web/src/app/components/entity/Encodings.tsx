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
// always paired with a label or a glyph, never colour alone. Magnitude
// (duration, counts) is one accent hue at one step — it is not run state and
// must never borrow the status ramp.
// ─────────────────────────────────────────────────────────────────────────────

import { type JSX, type ReactNode, useId } from "react";

import { STATUS_GROUPS, type StatusGroupId } from "@/app/runs/statusGroups";
import { WorkbenchAction } from "@/components/workbench";
import { formatDurationCompact } from "@/lib/format-time";
import { cn } from "@/lib/utils";

import type { StatusCountRollup } from "./Dashboard";
import { StatusDistribution } from "./Dashboard";

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
 * spread does — a bimodal duration histogram is how a degraded backend shows up
 * before anything has failed.
 */
export const Histogram = ({
  values,
  bins = 12,
  format,
  unit,
  ariaLabel,
  className,
}: HistogramProps): JSX.Element | null => {
  if (values.length === 0) return null;

  const sorted = [...values].sort((left, right) => left - right);
  const min = sorted[0] ?? 0;
  const max = sorted[sorted.length - 1] ?? 0;
  const median = quantile(sorted, 0.5);
  const buckets = histogramBuckets(sorted, bins);
  const peak = Math.max(...buckets.map((bucket) => bucket.count), 1);

  return (
    <div className={cn("space-y-2", className)}>
      <div role="img" aria-label={ariaLabel} className="flex h-16 items-end gap-hairline">
        {buckets.map((bucket) => (
          <span
            key={`${bucket.from}-${bucket.to}`}
            title={`${format(bucket.from)} – ${format(bucket.to)}: ${bucket.count} ${unit}`}
            className="flex-1 rounded-t-[2px] bg-accent/40"
            style={{
              height: `${Math.max(bucket.count > 0 ? 6 : 2, (bucket.count / peak) * 100)}%`,
            }}
          />
        ))}
      </div>
      <div className="flex items-baseline justify-between gap-2 font-mono text-micro tabular-nums text-muted-foreground">
        <span>{format(min)}</span>
        <span className="text-foreground">median {format(median)}</span>
        <span>{format(max)}</span>
      </div>
      <p className="text-micro text-muted-foreground">
        {sorted.length} {unit}
      </p>
    </div>
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

const SCHEDULE_LABEL = "minmax(0,16rem)";

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
 */
export const Schedule = ({ items, empty, className }: ScheduleProps): ReactNode => {
  const now = Date.now();
  const starts = items.map((item) => item.start).filter((value): value is number => value !== null);
  if (starts.length === 0) return empty ?? null;

  const min = Math.min(...starts);
  const max = Math.max(...items.map((item) => item.end ?? now), min + 1);
  const span = Math.max(1, max - min);

  return (
    <div className={className}>
      <ol className="divide-y divide-border/50 border-y border-border/70">
        {items.map((item) => {
          const start = item.start;
          const end = item.end ?? now;
          const left = start === null ? 0 : ((start - min) / span) * 100;
          const width = start === null ? 0 : Math.max(1.5, ((end - start) / span) * 100);
          const fill = item.status ? STATUS_FILL[item.status] : "bg-muted-foreground/40";
          const duration =
            start === null ? "" : formatDurationCompact(Math.max(0, end - start) / 1000);
          const detail = [
            item.detail,
            duration,
            item.end === null && start !== null ? "running" : null,
          ]
            .filter((part) => part != null && part !== "")
            .join(" · ");
          const row = (
            <span
              className="grid min-w-0 items-center gap-3 px-2 py-2"
              style={{ gridTemplateColumns: `${SCHEDULE_LABEL} minmax(0,1fr)` }}
            >
              <span className="min-w-0">
                <span className="flex min-w-0 items-center gap-2">
                  <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", fill)} />
                  <span className="truncate text-micro font-medium text-foreground">
                    {item.label}
                  </span>
                </span>
                {detail !== "" && (
                  <span className="block truncate pl-3 text-micro text-muted-foreground">
                    {detail}
                  </span>
                )}
              </span>
              <span className="relative h-4 border-x border-border/60">
                {start !== null && (
                  <span
                    className={cn(
                      "absolute top-1/2 h-1.5 -translate-y-1/2 rounded-control",
                      fill,
                      item.end === null && "opacity-70",
                    )}
                    style={{ left: `${left}%`, width: `${Math.min(100 - left, width)}%` }}
                  />
                )}
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
      <div
        className="grid items-center gap-3 px-2 pt-1 font-mono text-micro tabular-nums text-muted-foreground"
        style={{ gridTemplateColumns: `${SCHEDULE_LABEL} minmax(0,1fr)` }}
      >
        <span />
        <span className="flex justify-between">
          <span>{formatScheduleAxis(min, span)}</span>
          <span>{formatScheduleAxis(max, span)}</span>
        </span>
      </div>
    </div>
  );
};

// ── StatusLegend + StatusBreakdown ───────────────────────────────────────────

/** One legend for a whole page of small multiples, so no bar is colour-alone. */
export const StatusLegend = ({ className }: { className?: string }): JSX.Element => (
  <ul className={cn("flex flex-wrap items-center gap-x-4 gap-y-1", className)}>
    {STATUS_GROUPS.map((group) => (
      <li key={group.id} className="flex items-center gap-2 text-micro text-muted-foreground">
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
        <p
          id={captionId}
          className="font-mono text-micro uppercase tracking-wider text-muted-foreground"
        >
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
              <StatusDistribution counts={group.counts} legend={false} className="min-w-0" />
              <span className="text-right font-mono text-label tabular-nums text-muted-foreground">
                {group.counts.total}
              </span>
            </>
          );
          const layout =
            "grid grid-cols-[minmax(6rem,9rem)_minmax(0,1fr)_2.5rem] items-center gap-3";
          return (
            <li key={group.id} className="min-w-0">
              {group.onSelect ? (
                <WorkbenchAction
                  kind="ghost"
                  size="content"
                  onClick={group.onSelect}
                  className={cn(layout, "w-full rounded-control px-1 py-1 text-left")}
                >
                  {body}
                </WorkbenchAction>
              ) : (
                <span className={cn(layout, "px-1 py-1")}>{body}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
};
