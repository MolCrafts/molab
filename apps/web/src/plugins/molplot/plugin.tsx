import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { ChartLine } from "lucide-react";
import { MolplotView } from "./MolplotView";
import { countPanels, MOLPLOT_FILES } from "./molplot-files";

const molplotPlugin: MolabPluginModule = {
  id: "molplot",
  name: "MolPlot",
  version: "1.0.0",
  description: "One figure of an attempt's metrics, in any format the reader registry reports.",
  activate: (api: PluginAPI) => {
    // molplot owns no format: whichever readers are contributed decide what
    // it can draw, and a new one needs no change here.
    api.runViews.register({
      id: "molplot",
      label: "MolPlot",
      icon: ChartLine,
      order: 10,
      files: MOLPLOT_FILES,
      count: countPanels,
      Component: MolplotView,
    });
  },
};

export default molplotPlugin;
