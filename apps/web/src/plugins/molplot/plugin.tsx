import { ChartNoAxesCombined } from "lucide-react";
import { lazy } from "react";
import { registerFileTypeContribution } from "@/app/registry";
import type { UiPluginModule } from "@/plugins/types";
import { isMlpMetricsSurface } from "./mlp-surface";
import { resolveMolplotMetricsTabBadgeCount } from "./tab-badge-count";

const RunMetricsTab = lazy(() =>
  import("./RunMetricsTab").then((module) => ({ default: module.RunMetricsTab })),
);
const MolplotObservablesTab = lazy(() =>
  import("./MolplotObservablesTab").then((module) => ({
    default: module.MolplotObservablesTab,
  })),
);

const isMlpPlotSurface = (file: { name: string; relPath: string }): boolean => {
  const path = `${file.relPath}`.toLowerCase().replace(/\\/g, "/");
  const name = file.name.toLowerCase();
  return name.endsWith(".mlp.vl.json") || path.endsWith(".mlp.vl.json");
};

const molplotPlugin: UiPluginModule = {
  id: "molplot",
  name: "MolPlot",
  description: "Metrics and plot tabs when a run has *.mlp.jsonl / *.mlp.vl.json.",
  userToggleable: true,
  register: () => {
    registerFileTypeContribution({
      id: "molplot:run-metrics",
      objectType: "run",
      value: "metrics",
      label: "Metrics",
      Icon: ChartNoAxesCombined,
      priority: 40,
      matcher: {
        patterns: ["**/*.mlp.jsonl"],
        matches: isMlpMetricsSurface,
      },
      resolveTabBadgeCount: resolveMolplotMetricsTabBadgeCount,
      Component: RunMetricsTab,
    });
    registerFileTypeContribution({
      id: "molplot:run-tab",
      objectType: "run",
      value: "plots",
      label: "MolPlot",
      Icon: ChartNoAxesCombined,
      priority: 45,
      matcher: {
        patterns: ["**/*.mlp.vl.json", "*.mlp.vl.json"],
        matches: isMlpPlotSurface,
      },
      Component: MolplotObservablesTab,
    });
  },
};

export default molplotPlugin;
