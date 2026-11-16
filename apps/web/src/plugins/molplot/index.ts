export type { LineChartConfig, LineSeriesConfig, VegaLiteSpec } from "@molcrafts/molplot";
export {
  ChartLegend,
  type ChartLegendPlacement,
  type ChartLegendProps,
  legendEntries,
} from "./ChartLegend";
export { ChartWorkbench, type ChartWorkbenchProps } from "./ChartWorkbench";
export { MolplotBarChart } from "./MolplotBarChart";
export { MolplotLineChart, type MolplotLineChartHandle } from "./MolplotLineChart";
export {
  type AggregateOp,
  type AggregateResult,
  type CollectResult,
  collectRunSeries,
  type MetricRunSource,
  type MetricsFetcher,
  pickKeySeries,
  type RunAllSeries,
  selectAggregateConfig,
  stepResets,
} from "./multiRunMetrics";
export { filterSpikes, smoothEma } from "./smoothing";

/**
 * molplot UI plugin — the MolPlot run view (`api.runViews`).
 *
 * It reads the files a contributed metric reader claims (molab's own
 * ``*.mlp.jsonl`` WAL is one such format) and the run's own Vega-Lite figures
 * (``*.mlp.vl.json``); ``*.mlp.index.json`` is a leftover host cache and is
 * never matched. See ``molplot-files.ts``.
 */

export { default } from "./plugin";
