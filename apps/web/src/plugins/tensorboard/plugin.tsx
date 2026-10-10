import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { lazy } from "react";

const TensorBoardTab = lazy(() =>
  import("./TensorBoardTab").then((module) => ({ default: module.TensorBoardTab })),
);

const tensorboardPlugin: MolabPluginModule = {
  id: "tensorboard",
  name: "TensorBoard",
  version: "1.0.0",
  description: "TensorBoard tab when tfevents files are discovered on a run.",
  activate: (api: PluginAPI) => {
    api.fileTypes.register({
      id: "tensorboard:run-tab",
      objectType: "run",
      value: "tensorboard",
      label: "TensorBoard",
      priority: 45,
      matcher: {
        patterns: ["events.out.tfevents.*", "**/events.out.tfevents.*"],
      },
      Component: TensorBoardTab,
    });
  },
};

export default tensorboardPlugin;
