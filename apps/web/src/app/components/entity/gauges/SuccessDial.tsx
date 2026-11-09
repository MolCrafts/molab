// ─────────────────────────────────────────────────────────────────────────────
// Success dial — a 240° arc whose segments are the finished outcomes, in
// order: completed, failed, cancelled. The completed segment starts at the
// dial's zero, so where it ends *is* the success rate, read against the ticks.
// Active work has not finished and never enters the arc. Drawn by Vega: each
// segment answers hover with its count and click with its status.
// ─────────────────────────────────────────────────────────────────────────────

import { type JSX, useMemo } from "react";

import {
  CHART_GROUPS,
  type ChartGroupId,
  FINISHED_GROUPS,
  type StatusCounts,
} from "@/app/status/vocabulary";
import { cn } from "@/lib/utils";

import { useStatusColors } from "../InstrumentChart";
import { successShare } from "./scale";
import { DIAL, dialRows, dialSpec } from "./vega/instrumentSpecs";
import { OverviewChart } from "./vega/OverviewChart";

const labelOf = (id: ChartGroupId): string =>
  CHART_GROUPS.find((group) => group.id === id)?.label ?? id;

interface SuccessDialProps {
  counts: StatusCounts;
  /** Click on a segment: the status it stands for. */
  onPick?: (status: ChartGroupId) => void;
  className?: string;
}

export const SuccessDial = ({ counts, onPick, className }: SuccessDialProps): JSX.Element => {
  const colors = useStatusColors();
  const share = successShare(counts);
  const finished = FINISHED_GROUPS.reduce((sum, id) => sum + counts[id], 0);
  const active = counts.running + counts.queued;
  const data = useMemo(
    () => ({
      dial: dialRows(
        FINISHED_GROUPS.map((id) => ({
          key: id,
          count: counts[id],
          color: colors?.[id] ?? "transparent",
          tip: `${labelOf(id)}: ${counts[id]} of ${finished} finished (${
            finished === 0 ? 0 : Math.round((counts[id] / finished) * 100)
          }%)`,
        })),
      ),
    }),
    [counts, colors, finished],
  );
  const label =
    share === null
      ? `No finished work yet; ${active} in flight`
      : `Success ${Math.round(share * 100)} percent of ${finished} finished: ${FINISHED_GROUPS.map(
          (id) => `${counts[id]} ${labelOf(id).toLowerCase()}`,
        ).join(", ")}`;

  return (
    <div className={cn("relative shrink-0", className)} style={{ width: DIAL.width }}>
      <OverviewChart
        label={label}
        spec={dialSpec}
        specKey="dial"
        data={data}
        width={DIAL.width}
        height={DIAL.height}
        onPick={onPick ? (key) => onPick(key as ChartGroupId) : undefined}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 flex flex-col items-center"
        style={{ top: DIAL.cy - 18 }}
      >
        <span className="text-display font-semibold leading-none tracking-tight tabular-nums text-foreground">
          {share === null ? active : Math.round(share * 100)}
          {share !== null ? (
            <span className="text-title font-normal text-muted-foreground">%</span>
          ) : null}
        </span>
      </div>
    </div>
  );
};
