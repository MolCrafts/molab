import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { lazy } from "react";

const DeltaFChart = lazy(() =>
  import("./DeltaFChart").then((module) => ({ default: module.DeltaFChart })),
);

const deltafPlugin: MolabPluginModule = {
  id: "deltaf",
  name: "ΔF",
  version: "1.0.0",
  description: "Force-deviation (ΔF) chart tab for phase-1 quantization runs.",
  activate: (api: PluginAPI) => {
    api.fileTypes.register({
      id: "deltaf:run-tab",
      objectType: "run",
      value: "deltaf",
      label: "ΔF",
      priority: 48,
      matcher: {
        patterns: ["phase1_df_report.json", "**/phase1_df_report.json"],
      },
      Component: DeltaFChart,
    });
  },
};

export default deltafPlugin;
