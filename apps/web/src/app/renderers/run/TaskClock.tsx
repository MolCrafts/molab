/**
 * An attempt's tasks on its clock (L04): glyph and name in a column, beside a
 * chart of neutral bars whose status shows only as an end mark; a task that
 * never ran says why in words. Shared by the run Overview and its Preview.
 */

import type { JSX } from "react";
import { StatusIcon, TaskClockChart } from "@/app/components/entity";
import type { ClockRow } from "@/app/renderers/run/runStory";
import { chartGroupOf } from "@/app/status/vocabulary";
import { cn } from "@/lib/utils";

/** The attempt's tasks: glyph and name beside a clock of neutral bars. */
export const TaskClock = ({
  rows,
  onPreviewTask,
  labelWidth = "w-32 sm:w-44",
}: {
  rows: readonly ClockRow[];
  onPreviewTask?: (taskId: string) => void;
  /** Width of the glyph + name column. */
  labelWidth?: string;
}): JSX.Element => {
  const started = rows.some((row) => row.start !== null);
  return (
    <div className="flex min-w-0 gap-4">
      <ul className={cn("shrink-0", labelWidth)}>
        {rows.map((row) => (
          <li key={row.key} className="h-6">
            <button
              type="button"
              title={row.tip}
              onClick={() => onPreviewTask?.(row.key)}
              className="flex h-6 w-full min-w-0 items-center gap-2 rounded-hairline px-1 text-left text-body text-foreground hover:bg-interactive focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <StatusIcon status={row.status} className="size-icon-sm shrink-0" />
              <span className="min-w-0 truncate">{row.label}</span>
            </button>
          </li>
        ))}
      </ul>
      {started ? (
        <div className="min-w-0 flex-1">
          <TaskClockChart
            label="The attempt's tasks on its clock"
            tasks={rows.map((row) => ({
              key: row.key,
              start: row.start,
              end: row.end,
              status: chartGroupOf(row.status),
              note: row.note,
              tip: row.tip,
            }))}
            onPick={onPreviewTask}
          />
        </div>
      ) : (
        <ul className="min-w-0 flex-1">
          {rows.map((row) => (
            <li key={row.key} className="flex h-6 items-center text-body text-muted-foreground">
              {row.note}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
