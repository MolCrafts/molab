/**
 * Writing (L10-1): documents last edited per day over the past two weeks, as
 * compact Vega bars in the accent colour. A bar's tooltip names the day.
 */

import { type JSX, useMemo } from "react";
import { asSpec, type OverviewPalette } from "@/app/components/entity/gauges/vega/common";
import { OverviewChart } from "@/app/components/entity/gauges/vega/OverviewChart";
import type { WritingDay } from "./overviewModel";

const HEIGHT = 56;

const writingSpec = (p: OverviewPalette) =>
  asSpec({
    height: HEIGHT,
    width: "container",
    data: { name: "days" },
    mark: { type: "bar", color: p.accent, cornerRadiusEnd: 2, tooltip: true },
    encoding: {
      x: { field: "day", type: "ordinal", sort: null, axis: null },
      y: { field: "edits", type: "quantitative", axis: null },
      tooltip: [
        { field: "day", title: "Day" },
        { field: "edits", title: "Documents edited" },
      ],
    },
    config: { view: { stroke: null } },
  });

export const WritingChart = ({ days }: { days: readonly WritingDay[] }): JSX.Element => {
  const data = useMemo(() => ({ days: days.map((day) => ({ ...day })) }), [days]);
  return (
    <OverviewChart
      label="Documents edited per day"
      spec={writingSpec}
      specKey={`writing:${days.length}`}
      data={data}
      height={HEIGHT}
    />
  );
};
