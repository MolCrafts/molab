import { lazy } from "react";
import { registerFileTypeContribution } from "@/app/registry";
import type { UiPluginModule } from "@/plugins/types";

const TensorBoardTab = lazy(() =>
  import("./TensorBoardTab").then((module) => ({ default: module.TensorBoardTab })),
);

const tensorboardPlugin: UiPluginModule = {
  id: "tensorboard",
  name: "TensorBoard",
  description: "TensorBoard tab when tfevents files are discovered on a run.",
  userToggleable: true,
  register: () => {
    registerFileTypeContribution({
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
