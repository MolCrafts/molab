// ─────────────────────────────────────────────────────────────────────────────
// Status overview: the shared arc chart shows the mix, with explicit counts
// and the success rate of finished work beside it.
// ─────────────────────────────────────────────────────────────────────────────

import { ArcChart } from "@molcrafts/ui-vega";
import { type JSX, useMemo } from "react";

import { STATUS_GROUPS } from "@/app/runs/statusGroups";
import { cn } from "@/lib/utils";

import { useStatusColors } from "../InstrumentChart";
import { type StatusCounts, successShare } from "./scale";

interface StatusLedgerProps {
  counts: StatusCounts;
  /** Singular and plural noun for one counted item. */
  unit?: readonly [string, string];
  /** The counts cover only what has loaded so far; say so beside the rate. */
  partial?: boolean;
  className?: string;
}

const plural = (count: number, [one, many]: readonly [string, string]): string =>
  count === 1 ? one : many;

export const StatusLedger = ({
  counts,
  unit = ["run", "runs"],
  partial = false,
  className,
}: StatusLedgerProps): JSX.Element => {
  const share = successShare(counts);
  const finished = counts.succeeded + counts.failed + counts.cancelled;
  const active = counts.running + counts.pending;
  const colors = useStatusColors();
  const shares = useMemo(
    () =>
      STATUS_GROUPS.map((group) => ({
        label: `${group.label} · ${counts[group.id]}`,
        value: counts[group.id],
        color: colors?.[group.id],
        tip: `${group.label}: ${counts[group.id]} ${plural(counts[group.id], unit)}`,
      })),
    [counts, colors, unit],
  );
  const summary = STATUS_GROUPS.map(
    (group) => `${counts[group.id]} ${group.label.toLowerCase()}`,
  ).join(", ");

  return (
    <div
      className={cn(
        "grid min-w-0 items-center gap-x-4 gap-y-2 sm:grid-cols-[minmax(0,8rem)_minmax(0,1fr)]",
        className,
      )}
    >
      <div className="min-w-0">
        {share !== null ? (
          <>
            <p className="text-heading font-semibold tracking-tight tabular-nums text-foreground">
              {Math.round(share * 100)}
              <span className="text-title font-normal text-muted-foreground">%</span>
            </p>
            <p className="text-label text-muted-foreground">
              success · <span className="font-mono tabular-nums text-foreground">{finished}</span>{" "}
              finished
              {partial ? ", loaded so far" : ""}
            </p>
          </>
        ) : (
          <>
            <p className="text-heading font-semibold tracking-tight tabular-nums text-foreground">
              {active}
            </p>
            <p className="text-label text-muted-foreground">
              {plural(active, unit)} in flight, none finished yet
            </p>
          </>
        )}
      </div>

      <ArcChart
        data={shares}
        label={`${counts.total} ${plural(counts.total, unit)}: ${summary}`}
        labelHidden
        height={136}
        loading={colors === null}
        className="min-w-0 w-full max-w-sm"
      />
    </div>
  );
};
