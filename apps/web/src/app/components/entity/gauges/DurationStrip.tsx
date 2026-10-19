// ─────────────────────────────────────────────────────────────────────────────
// Duration strip — every finished run is one dot on a shared time axis. A
// histogram of seven runs is mostly empty bins; a dot per run shows the spread,
// the outlier and the outcome at once, and stays honest at n = 1.
// Several series share one axis, so experiments compare by position.
// ─────────────────────────────────────────────────────────────────────────────

import type { JSX, ReactNode } from "react";
import { Link } from "react-router-dom";

import { STATUS_GROUPS, type StatusGroupId } from "@/app/runs/statusGroups";
import { cn } from "@/lib/utils";

import { STATUS_FILL } from "./Gauge";
import { formatSpan, quantile, spanScale, stackLanes } from "./scale";

export interface DurationPoint {
  id: string;
  seconds: number;
  status: StatusGroupId | null;
  label: string;
  href?: string;
}

export interface DurationSeries {
  id: string;
  label?: ReactNode;
  points: DurationPoint[];
}

/** Vertical pitch of one stacked lane, in px. Dots are 8px; 2px air. */
const LANE_PX = 10;

const statusWord = (status: StatusGroupId | null): string =>
  STATUS_GROUPS.find((group) => group.id === status)?.label ?? "Unknown";

const pct = (fraction: number): string => `${(fraction * 100).toFixed(3)}%`;

const Dot = ({
  point,
  left,
  lane,
}: {
  point: DurationPoint;
  left: number;
  lane: number;
}): JSX.Element => {
  const title = `${point.label} · ${formatSpan(point.seconds)} · ${statusWord(point.status)}`;
  const className = cn(
    "absolute top-1/2 size-2 rounded-full ring-2 ring-background transition-transform duration-150",
    "hover:scale-150 focus-visible:scale-150 focus-visible:outline-none focus-visible:ring-ring",
    point.status ? STATUS_FILL[point.status] : "bg-muted-foreground",
  );
  const style = {
    left: pct(left),
    transform: `translate(-50%, calc(-50% + ${lane * LANE_PX}px))`,
  };
  return point.href ? (
    <Link to={point.href} title={title} aria-label={title} className={className} style={style} />
  ) : (
    <span role="img" title={title} aria-label={title} className={className} style={style} />
  );
};

export const DurationStrip = ({
  series,
  className,
}: {
  series: DurationSeries[];
  className?: string;
}): JSX.Element | null => {
  const all = series.flatMap((item) => item.points.map((point) => point.seconds));
  if (all.length === 0) return null;
  const scale = spanScale(all);
  const labelled = series.some((item) => item.label != null);
  const columns = labelled
    ? "grid-cols-[minmax(0,10rem)_minmax(0,1fr)_minmax(0,4rem)]"
    : "grid-cols-[minmax(0,1fr)]";

  return (
    <div className={cn("min-w-0", className)}>
      <ol className="min-w-0">
        {series.map((item) => {
          const positions = item.points.map((point) => scale.at(point.seconds));
          const lanes = stackLanes(positions);
          const depth = Math.max(0, ...lanes.map(Math.abs));
          const sorted = item.points.map((point) => point.seconds).sort((a, b) => a - b);
          const median = quantile(sorted, 0.5);
          const low = quantile(sorted, 0.25);
          const high = quantile(sorted, 0.75);
          return (
            <li key={item.id} className={cn("grid min-w-0 items-center gap-x-4", columns)}>
              {labelled ? (
                <span className="min-w-0 truncate text-label text-foreground">{item.label}</span>
              ) : null}
              <span
                className="relative block"
                style={{ height: `${Math.max(28, (depth * 2 + 1) * LANE_PX + 12)}px` }}
              >
                {scale.ticks.map((tick) => (
                  <span
                    key={tick}
                    aria-hidden
                    className="absolute inset-y-0 w-px bg-border/60"
                    style={{ left: pct(scale.at(tick)) }}
                  />
                ))}
                <span aria-hidden className="absolute inset-x-0 top-1/2 h-px bg-border" />
                {sorted.length > 1 ? (
                  <span
                    aria-hidden
                    title={`Middle half: ${formatSpan(low)} to ${formatSpan(high)}`}
                    className="absolute top-1/2 h-3 -translate-y-1/2 rounded-hairline bg-muted"
                    style={{
                      left: pct(scale.at(low)),
                      width: `max(2px, ${pct(scale.at(high) - scale.at(low))})`,
                    }}
                  />
                ) : null}
                <span
                  aria-hidden
                  title={`Median ${formatSpan(median)}`}
                  className="absolute inset-y-1 w-px bg-foreground"
                  style={{ left: pct(scale.at(median)) }}
                />
                {item.points.map((point, index) => (
                  <Dot
                    key={point.id}
                    point={point}
                    left={positions[index] ?? 0}
                    lane={lanes[index] ?? 0}
                  />
                ))}
              </span>
              {labelled ? (
                <span className="text-right font-mono text-label tabular-nums text-muted-foreground">
                  {formatSpan(median)}
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
      <div className={cn("grid min-w-0 gap-x-4 pt-1", columns)}>
        {labelled ? <span /> : null}
        <span aria-hidden className="relative block h-4">
          {scale.ticks.map((tick, index) => {
            const at = scale.at(tick);
            const edge = index === 0 && at < 0.04 ? "0%" : at > 0.96 ? "-100%" : "-50%";
            return (
              <span
                key={tick}
                className="absolute top-0 whitespace-nowrap font-mono text-micro tabular-nums text-muted-foreground"
                style={{ left: pct(at), transform: `translateX(${edge})` }}
              >
                {formatSpan(tick)}
              </span>
            );
          })}
        </span>
        {labelled ? (
          <span className="text-right text-micro text-muted-foreground">median</span>
        ) : null}
      </div>
    </div>
  );
};
