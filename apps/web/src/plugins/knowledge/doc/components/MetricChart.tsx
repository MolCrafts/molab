/**
 * `<molab-metric-chart experiment=… y=… x=… by=… caption=…>` (L10): a metric
 * across a swept parameter, one line per value of `by`, drawn with the
 * experiment Overview's key-result spec (`sweepSpec`). A failed run is a ✗ in
 * the failure colour at its x. A click on a point previews its run.
 */

import { ChartLine } from "lucide-react";
import { type JSX, useMemo } from "react";
import { SWEEP_HEIGHT } from "@/app/components/entity/gauges/vega/chartSpecs";
import { OverviewChart } from "@/app/components/entity/gauges/vega/OverviewChart";
import { usePreview } from "@/app/preview/PreviewContext";
import type { RunSummary } from "@/app/types";
import type { DocComponentProps, DocComponentSpec } from "../context";
import { ComponentFrame, ComponentLoading, ComponentNotice } from "../frame";
import { runPreviewTarget, useDocExperiment, useRunResults } from "./docRuns";
import { metricChartData, metricSpec } from "./metricChartModel";

const NAME = "molab-metric-chart";

const NO_RUNS: readonly RunSummary[] = [];

const Header = ({ title, aside }: { title: string; aside: string }): JSX.Element => (
  <div className="flex h-control-compact items-center gap-3 px-3">
    <span className="min-w-0 truncate font-medium text-foreground">{title}</span>
    <span className="ml-auto flex-none text-label text-muted-foreground tabular-nums">{aside}</span>
  </div>
);

export const MetricChart = ({ attrs }: DocComponentProps): JSX.Element => {
  const { x, y, by, caption } = attrs;
  const preview = usePreview();
  const found = useDocExperiment(attrs.experiment);
  const runs = found?.runs ?? NO_RUNS;
  const yIsParameter = y ? runs.some((run) => y in (run.parameters ?? {})) : false;
  const results = useRunResults(found?.experiment.id ?? null, Boolean(y) && !yIsParameter);
  const data = useMemo(
    () =>
      x && y
        ? metricChartData(
            runs.map((run) => ({ ...run, parameters: run.parameters ?? {} })),
            { x, y, ...(by ? { by } : {}) },
            (id) => results.byRun.get(id),
          )
        : null,
    [runs, x, y, by, results.byRun],
  );
  const chartData = useMemo(() => ({ points: data?.rows ?? [] }), [data]);

  if (!attrs.experiment || !x || !y) {
    return <ComponentNotice name={NAME}>Needs experiment=, x= and y= attributes.</ComponentNotice>;
  }
  if (!found) {
    return <ComponentNotice name={NAME}>{attrs.experiment} does not resolve.</ComponentNotice>;
  }
  if (!data || data.withValue === 0) {
    return results.loading ? (
      <ComponentLoading name={NAME} />
    ) : (
      <ComponentNotice name={NAME}>No values for {y} yet.</ComponentNotice>
    );
  }
  const openRun = (key: string): void => {
    const run = runs.find((item) => item.id === key);
    if (run) preview.preview(runPreviewTarget(run));
  };
  const runCount = data.rows.length;
  return (
    <ComponentFrame label={`${y} across ${x}`}>
      <Header
        title={`${y} across ${x}`}
        aside={`${runCount} ${runCount === 1 ? "run" : "runs"} · live`}
      />
      <div className="px-3">
        <OverviewChart
          label={`${y} of every run across ${x}${by ? `, one line per ${by}` : ""}`}
          spec={(palette) => metricSpec(palette, data.axis)}
          specKey={`metric:${data.axis.labels.join(",")}:${data.axis.log}:${data.axis.domain.join(",")}`}
          data={chartData}
          height={SWEEP_HEIGHT + 24}
          onPick={openRun}
        />
      </div>
      {caption ? <p className="px-3 pb-2 text-label text-muted-foreground">{caption}</p> : null}
    </ComponentFrame>
  );
};

export const metricChartSpec: DocComponentSpec = {
  name: NAME,
  label: "Metric chart",
  description: "A metric across a swept parameter, one line per series; points preview their run",
  keywords: ["chart", "metric", "plot", "sweep", "vega", "result"],
  icon: ChartLine,
  template: { experiment: "molab:experiment/", x: "", y: "" },
  Component: MetricChart,
};
