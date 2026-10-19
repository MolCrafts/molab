// ─────────────────────────────────────────────────────────────────────────────
// Overview composition: a lead that spans the page, then a wide main column of
// gauges beside a narrow margin of notes. The two columns stack at their own
// rhythm, so their rules land at different heights — the page reads as a
// composed sheet, not a grid of matching tiles.
// ─────────────────────────────────────────────────────────────────────────────

import type { JSX, ReactNode } from "react";

import { cn } from "@/lib/utils";

export const OverviewSheet = ({
  lead,
  main,
  margin,
  className,
}: {
  /** Spans both columns: the ledger, or the run's one-line verdict. */
  lead?: ReactNode;
  main: ReactNode;
  /** Narrow column of notes. Omitted, the main column takes the width. */
  margin?: ReactNode;
  className?: string;
}): JSX.Element => (
  <div className={cn("min-w-0 space-y-4 pb-2", className)}>
    {lead != null ? <div className="min-w-0">{lead}</div> : null}
    <div
      className={cn(
        "grid min-w-0 items-start gap-x-6 gap-y-4",
        margin != null && "lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]",
      )}
    >
      <div className="min-w-0 space-y-4">{main}</div>
      {margin != null ? <aside className="min-w-0 space-y-4">{margin}</aside> : null}
    </div>
  </div>
);
