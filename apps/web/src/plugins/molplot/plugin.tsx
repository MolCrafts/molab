import { ChartNoAxesCombined } from "lucide-react";
import { registerFileTypeContribution } from "@/app/registry";
import type { UiPluginModule } from "@/plugins/types";
import { isMlpMetricsSurface } from "./mlp-surface";
import { resolveMolplotMetricsTabBadgeCount } from "./tab-badge-count";
import { MolplotRunTab } from "./MolplotRunTab";

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
      id: "molplot:run-tab",
      objectType: "run",
      value: "molplot",
      label: "MolPlot",
      Icon: ChartNoAxesCombined,
      priority: 40,
      matcher: {
        patterns: ["**/*.mlp.jsonl", "**/*.mlp.vl.json", "*.mlp.vl.json"],
        matches: (file) => isMlpMetricsSurface(file) || isMlpPlotSurface(file),
      },
      resolveTabBadgeCount: resolveMolplotMetricsTabBadgeCount,
      Component: MolplotRunTab,
    });
  },
};

export default molplotPlugin;
