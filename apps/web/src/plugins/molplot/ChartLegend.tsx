/**
 * The legend, drawn in HTML rather than inside the canvas.
 *
 * Vega renders its legend into the plot: it competes with the curves for
 * width, it truncates a label at a pixel budget with no way to see the rest,
 * and it lays entries out however it likes. That is bearable for `loss` and
 * `energy`; a cross-run comparison labels its series with run ancestry —
 * `peo-polar/n-series/n=8` — where the clipped half is exactly the half that
 * tells two runs apart.
 *
 * Out here the label can be truncated *and* recoverable: the full name is one
 * hover away, and a legend long enough to crowd the plot scrolls in its own
 * column instead of squeezing it.
 *
 * A legend is read down, not across — one label per line, swatches aligned in
 * a single column — so both placements are vertical. `right` gives it a strip
 * of its own, which is what a wide surface can afford; `overlay` floats it in
 * the plot's top-right corner, for a chart small enough that a strip would
 * cost more than the corner it covers.
 *
 * One entry per *label*, not per series. Colour follows the group — every seed
 * of one experiment is one colour and one legend row — so the count of series
 * behind a row is what says "five runs", and repeating the row five times
 * would say nothing.
 */

import type { JSX } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { CHART_SERIES_PALETTE } from "@/lib/chart-tokens";
import { cn } from "@/lib/utils";

/** As much of a series as a legend needs; matches molplot's `LineSeriesConfig`. */
export interface LegendSeries {
  id: string;
  label?: string;
  color?: string;
}

export interface LegendEntry {
  label: string;
  color: string;
  /** How many series share this label — the runs behind one colour. */
  count: number;
}

/**
 * One entry per distinct label, in the order the series were built.
 *
 * The first series of a label owns its colour, which is what the chart draws;
 * a series with no colour falls back to the palette by entry position, so a
 * legend never renders a swatch the plot does not have.
 */
export const legendEntries = (
  series: readonly LegendSeries[],
  palette: readonly string[] = CHART_SERIES_PALETTE,
): LegendEntry[] => {
  const byLabel = new Map<string, LegendEntry>();
  for (const item of series) {
    const label = item.label ?? item.id;
    const seen = byLabel.get(label);
    if (seen) {
      seen.count += 1;
      continue;
    }
    byLabel.set(label, {
      label,
      color: item.color ?? palette[byLabel.size % palette.length],
      count: 1,
    });
  }
  return Array.from(byLabel.values());
};

/**
 * `right` needs a row-direction parent; `overlay` needs a positioned one
 * (the plot's own box), and covers the corner of the plot rather than
 * taking width from it.
 */
export type ChartLegendPlacement = "right" | "overlay";

const PLACEMENT_CLASS: Record<ChartLegendPlacement, string> = {
  right: "min-h-0 w-48 shrink-0 border-l border-border px-3 py-3",
  overlay:
    "absolute top-2 right-2 z-10 max-h-[calc(100%-1rem)] max-w-[45%] rounded-control border border-border bg-background/90 px-2 py-row-pad",
};

export interface ChartLegendProps {
  series: readonly LegendSeries[];
  placement?: ChartLegendPlacement;
  /**
   * Hidden below this many entries. One row naming what the title and the y
   * axis already name is noise, so a single-series chart gets no legend.
   */
  minEntries?: number;
  className?: string;
}

export const ChartLegend = ({
  series,
  placement = "right",
  minEntries = 2,
  className,
}: ChartLegendProps): JSX.Element | null => {
  const entries = legendEntries(series);
  if (entries.length < minEntries) return null;

  return (
    <ul
      aria-label="Series"
      className={cn(
        "flex max-h-full flex-col gap-1 overflow-y-auto",
        PLACEMENT_CLASS[placement],
        className,
      )}
    >
      {entries.map((entry) => (
        <li key={entry.label} className="flex min-w-0 items-center gap-2">
          {/* A stroke, not a dot: the mark it stands for is a line. */}
          <span
            aria-hidden
            className="h-0.5 w-3 flex-none rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="min-w-0 truncate font-mono text-micro text-muted-foreground">
                {entry.label}
              </span>
            </TooltipTrigger>
            <TooltipContent side="left" className="max-w-md">
              <span className="font-mono text-micro">{entry.label}</span>
            </TooltipContent>
          </Tooltip>
          {entry.count > 1 && (
            <span className="flex-none font-mono text-micro text-muted-foreground/70 tabular-nums">
              ×{entry.count}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
};
