import { lazy } from "react";
import { registerFileTypeContribution } from "@/app/registry";
import type { UiPluginModule } from "@/plugins/types";

const DeltaFChart = lazy(() =>
  import("./DeltaFChart").then((module) => ({ default: module.DeltaFChart })),
);

const deltafPlugin: UiPluginModule = {
  id: "deltaf",
  name: "ΔF",
  description: "Force-deviation (ΔF) chart tab for phase-1 quantization runs.",
  userToggleable: true,
  register: () => {
    registerFileTypeContribution({
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
