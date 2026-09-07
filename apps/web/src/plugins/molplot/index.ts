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
export { MolplotRawChart } from "./MolplotRawChart";
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
export { RunMetricsTab } from "./RunMetricsTab";
export { RunMetricsView } from "./RunMetricsView";
export { filterSpikes, smoothEma } from "./smoothing";

/**
 * molplot UI plugin — activates purely by filename suffixes (no heuristics).
 *
 * Contract (see molexp.workspace.mlp_names):
 * - ``*.mlp.jsonl`` — live metrics WAL → Metrics tab
 * - leftover ``*.mlp.zarr`` is not a metrics surface
 * - ``*.mlp.vl.json`` — Vega-Lite plot artifact → MolPlot tab
 * - ``*.mlp.index.json`` is a leftover host cache — never matched
 */

export { default } from "./plugin";
