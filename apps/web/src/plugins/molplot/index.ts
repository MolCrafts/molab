export type { LineChartConfig, LineSeriesConfig, VegaLiteSpec } from "@molcrafts/molplot";
export { MolplotBarChart } from "./MolplotBarChart";
export { MolplotGanttChart } from "./MolplotGanttChart";
export { MolplotLineChart, type MolplotLineChartHandle } from "./MolplotLineChart";
export { MolplotRawChart } from "./MolplotRawChart";
export { MultiRunMetricsView } from "./MultiRunMetricsView";
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
