/** Compact parameter values and run counts; individual runs live in the Runs table. */

import type { JSX } from "react";

import { cn } from "@/lib/utils";

export interface SweepCell {
  value: string;
  /** The run did not carry this parameter at all. */
  unset: boolean;
  runCount: number;
}

export interface SweepAxis {
  key: string;
  cells: SweepCell[];
}

const Cell = ({ cell }: { cell: SweepCell }): JSX.Element => {
  const empty = cell.runCount === 0;
  return (
    <li className="inline-flex items-baseline gap-2 py-1 pr-4">
      <span
        className={cn(
          "max-w-32 truncate font-mono text-label tabular-nums",
          cell.unset ? "italic text-muted-foreground" : "text-foreground",
        )}
        title={cell.value}
      >
        {cell.value}
      </span>
      <span className="text-micro tabular-nums text-muted-foreground">
        {empty ? "not run" : `${cell.runCount} ${cell.runCount === 1 ? "run" : "runs"}`}
      </span>
    </li>
  );
};

export const SweepMatrix = ({
  axes,
  className,
}: {
  axes: SweepAxis[];
  className?: string;
}): JSX.Element => (
  <dl className={cn("min-w-0 divide-y divide-border/60", className)}>
    {axes.map((axis) => (
      <div
        key={axis.key}
        className="grid min-w-0 gap-x-6 gap-y-2 py-3 first:pt-0 sm:grid-cols-[minmax(0,7rem)_minmax(0,1fr)]"
      >
        <dt
          className="min-w-0 truncate pt-1 font-mono text-label text-muted-foreground"
          title={axis.key}
        >
          {axis.key}
        </dt>
        <dd className="min-w-0">
          <ul className="flex flex-wrap gap-2">
            {axis.cells.map((cell) => (
              <Cell key={`${cell.unset ? "unset" : "value"}:${cell.value}`} cell={cell} />
            ))}
          </ul>
        </dd>
      </div>
    ))}
  </dl>
);
