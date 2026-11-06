import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { ChartNoAxesCombined } from "lucide-react";
import { MolplotRunTab } from "./MolplotRunTab";
import { isMetricSurface } from "./metric-formats";
import { resolveMolplotMetricsTabBadgeCount } from "./tab-badge-count";

const isMlpPlotSurface = (file: { name: string; relPath: string }): boolean => {
  const path = `${file.relPath}`.toLowerCase().replace(/\\/g, "/");
  const name = file.name.toLowerCase();
  return name.endsWith(".mlp.vl.json") || path.endsWith(".mlp.vl.json");
};

const molplotPlugin: MolabPluginModule = {
  id: "molplot",
  name: "MolPlot",
  version: "1.0.0",
  description: "Metrics and plot tabs for any format the reader registry reports.",
  activate: (api: PluginAPI) => {
    // molplot owns no format: whichever readers are contributed decide what
    // it can draw, and a new one needs no change here.
    api.fileTypes.register({
      id: "molplot:run-tab",
      objectType: "run",
      value: "molplot",
      label: "MolPlot",
      Icon: ChartNoAxesCombined,
      priority: 40,
      matcher: {
        // Vega-Lite plots are molplot's own artifact, so they stay a literal
        // pattern; everything else is whatever the registry claims.
        patterns: ["**/*.mlp.vl.json", "*.mlp.vl.json"],
        matches: (file) => isMetricSurface(file) || isMlpPlotSurface(file),
      },
      resolveTabBadgeCount: resolveMolplotMetricsTabBadgeCount,
      Component: MolplotRunTab,
    });
  },
};

export default molplotPlugin;
