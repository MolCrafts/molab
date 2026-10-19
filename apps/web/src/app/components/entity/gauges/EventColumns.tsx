// ─────────────────────────────────────────────────────────────────────────────
// Event columns — work entering and leaving, on one clock. Starts rise above
// the axis; finishes hang below it, stacked by outcome. Two flows, one shared
// magnitude, so a backlog (starts outrunning finishes) is visible as a shape.
// ─────────────────────────────────────────────────────────────────────────────

import type { JSX } from "react";

import { cn } from "@/lib/utils";

import type { TimeBucket } from "./scale";

const FINISH_LAYERS = [
  { key: "succeeded", label: "succeeded", fill: "bg-status-completed" },
  { key: "failed", label: "failed", fill: "bg-status-failed" },
  { key: "cancelled", label: "cancelled", fill: "bg-status-cancelled" },
  { key: "other", label: "other", fill: "bg-muted-foreground" },
] as const;

const pad2 = (value: number): string => value.toString().padStart(2, "0");

const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;

/** Clock for a day window, weekday for a week window. */
export const bucketTick = (ms: number, windowMs: number): string => {
  const date = new Date(ms);
  if (windowMs <= 36 * 60 * 60 * 1000) return `${pad2(date.getHours())}:00`;
  return WEEKDAY[date.getDay()] ?? "";
};

const finishedIn = (bucket: TimeBucket): number =>
  bucket.finishes.succeeded +
  bucket.finishes.failed +
  bucket.finishes.cancelled +
  bucket.finishes.other;

interface EventColumnsProps {
  buckets: TimeBucket[];
  windowMs: number;
  showStarts: boolean;
  showFinishes: boolean;
  /** Label every n-th bucket on the axis. */
  tickEvery: number;
  className?: string;
}

export const EventColumns = ({
  buckets,
  windowMs,
  showStarts,
  showFinishes,
  tickEvery,
  className,
}: EventColumnsProps): JSX.Element => {
  const peak = Math.max(
    1,
    ...buckets.map((bucket) =>
      Math.max(showStarts ? bucket.starts : 0, showFinishes ? finishedIn(bucket) : 0),
    ),
  );
  const height = (value: number): string => `${(value / peak) * 100}%`;
  const describe = (bucket: TimeBucket): string => {
    const parts = [`${bucketTick(bucket.start, windowMs)} – ${bucketTick(bucket.end, windowMs)}`];
    if (showStarts) parts.push(`${bucket.starts} started`);
    if (showFinishes) {
      const outcomes = FINISH_LAYERS.filter((layer) => bucket.finishes[layer.key] > 0)
        .map((layer) => `${bucket.finishes[layer.key]} ${layer.label}`)
        .join(", ");
      parts.push(`${finishedIn(bucket)} finished${outcomes ? ` (${outcomes})` : ""}`);
    }
    return parts.join(" · ");
  };

  return (
    <div className={cn("flex h-full min-h-28 min-w-0 flex-col", className)}>
      <div className="grid min-h-0 flex-1 grid-cols-[2.5rem_minmax(0,1fr)] gap-x-2">
        <div className="flex flex-col justify-between py-1 text-right font-mono text-micro tabular-nums text-muted-foreground">
          <span>{showStarts ? peak : ""}</span>
          <span className="text-foreground">0</span>
          <span>{showFinishes ? peak : ""}</span>
        </div>
        <ol className="relative flex min-h-0 gap-hairline">
          <span aria-hidden className="absolute inset-x-0 top-1/2 h-px bg-foreground/70" />
          {buckets.map((bucket) => (
            <li
              key={bucket.start}
              title={describe(bucket)}
              className="group flex min-w-0 flex-1 flex-col hover:bg-interactive"
            >
              <span className="flex flex-1 items-end">
                {showStarts && bucket.starts > 0 ? (
                  <span
                    className="w-full rounded-t-hairline bg-foreground"
                    style={{ height: height(bucket.starts) }}
                  />
                ) : null}
              </span>
              <span className="flex flex-1 flex-col">
                {showFinishes
                  ? FINISH_LAYERS.map((layer) =>
                      bucket.finishes[layer.key] > 0 ? (
                        <span
                          key={layer.key}
                          className={cn("w-full first:mt-px last:rounded-b-hairline", layer.fill)}
                          style={{ height: height(bucket.finishes[layer.key]) }}
                        />
                      ) : null,
                    )
                  : null}
              </span>
            </li>
          ))}
        </ol>
      </div>
      <div className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-2 pt-1">
        <span />
        <ol
          aria-hidden
          className="flex gap-hairline font-mono text-micro tabular-nums text-muted-foreground"
        >
          {buckets.map((bucket, index) => (
            <li key={bucket.start} className="relative h-4 min-w-0 flex-1">
              {index === buckets.length - 1 ? (
                <span className="absolute right-0 text-foreground">now</span>
              ) : index % tickEvery === 0 && buckets.length - 1 - index > tickEvery / 2 ? (
                <span className="absolute left-0 whitespace-nowrap">
                  {bucketTick(bucket.start, windowMs)}
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
};

/** Legend line for the readout: what is above the axis and what is below. */
export const EventLegend = ({
  showStarts,
  showFinishes,
}: {
  showStarts: boolean;
  showFinishes: boolean;
}): JSX.Element => (
  <span className="inline-flex items-center gap-4">
    {showStarts ? (
      <span className="inline-flex items-center gap-1">
        <span aria-hidden className="size-2 rounded-hairline bg-foreground" />
        Started
      </span>
    ) : null}
    {showFinishes ? (
      <span className="inline-flex items-center gap-1">
        <span aria-hidden className="flex h-2 w-3 overflow-hidden rounded-hairline">
          <span className="flex-1 bg-status-completed" />
          <span className="flex-1 bg-status-failed" />
        </span>
        Finished
      </span>
    ) : null}
  </span>
);
