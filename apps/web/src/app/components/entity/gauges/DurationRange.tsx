// ─────────────────────────────────────────────────────────────────────────────
// Duration range — the spread of finished runs on one scale: the whisker is
// fastest to slowest, the box is the middle half, the rule is the median. A
// median alone changes no decision; whether the slow tail is 2× or 20× does.
// Drawn by Vega; each part names its numbers on hover.
// ─────────────────────────────────────────────────────────────────────────────

import { type JSX, useMemo } from "react";

import { formatSpan, quantile, spanScale } from "./scale";
import { RANGE_HEIGHT, rangeSpec } from "./vega/instrumentSpecs";
import { OverviewChart } from "./vega/OverviewChart";

interface DurationRangeProps {
  /** Seconds per finished run. */
  seconds: readonly number[];
  className?: string;
}

export const DurationRange = ({ seconds, className }: DurationRangeProps): JSX.Element | null => {
  const summary = useMemo(() => {
    if (seconds.length === 0) return null;
    const sorted = [...seconds].sort((left, right) => left - right);
    const scale = spanScale(sorted);
    const ticks = scale.ticks.filter((_, index, all) => all.length <= 4 || index % 2 === 0);
    return {
      axis: { domain: scale.domain, ticks, log: scale.log },
      min: sorted[0] ?? 0,
      max: sorted[sorted.length - 1] ?? 0,
      low: quantile(sorted, 0.25),
      high: quantile(sorted, 0.75),
      median: quantile(sorted, 0.5),
    };
  }, [seconds]);
  const data = useMemo(() => {
    if (!summary) return { range: [] };
    const { min, max, low, high, median } = summary;
    return {
      range: [
        {
          key: "whisker",
          part: "whisker",
          from: min,
          to: max,
          tip: `Fastest ${formatSpan(min)} · slowest ${formatSpan(max)}`,
        },
        {
          key: "box",
          part: "box",
          from: low,
          to: high,
          tip: `Middle half ${formatSpan(low)} – ${formatSpan(high)}`,
        },
        {
          key: "median",
          part: "median",
          from: median,
          to: median,
          tip: `Median ${formatSpan(median)}`,
        },
      ],
    };
  }, [summary]);
  if (!summary) return null;
  const { axis, min, max, low, high, median } = summary;
  const label = `Fastest ${formatSpan(min)}, middle half ${formatSpan(low)} to ${formatSpan(
    high,
  )}, median ${formatSpan(median)}, slowest ${formatSpan(max)}`;
  return (
    <OverviewChart
      label={label}
      spec={(palette) => rangeSpec(palette, axis)}
      specKey={`range:${axis.domain.join(",")}:${axis.log}:${axis.ticks.join(",")}`}
      data={data}
      height={RANGE_HEIGHT}
      className={className}
    />
  );
};
