import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { Atom } from "lucide-react";
import { lazyWithPrefetch } from "@/lib/lazy-with-prefetch";
import { isMolvisOpenable } from "./openable";

const MolvisDatasetPreview = lazyWithPrefetch(() =>
  import("./MolvisDatasetPreview").then((module) => ({
    default: module.MolvisDatasetPreview,
  })),
);
const MolvisTab = lazyWithPrefetch(() =>
  import("./MolvisTab").then((module) => ({ default: module.MolvisTab })),
);

const molvisPlugin: MolabPluginModule = {
  id: "molvis",
  name: "MolVis",
  version: "1.0.0",
  description:
    "Trajectory and structure viewer tab when a run has PDB/XYZ/LAMMPS dumps or a *.mrec store.",
  activate: (api: PluginAPI) => {
    api.fileTypes.register({
      id: "molvis:run-tab",
      objectType: "run",
      value: "molvis",
      label: "MolVis",
      Icon: Atom,
      priority: 40,
      matcher: {
        matches: isMolvisOpenable,
      },
      Component: MolvisTab,
    });

    api.filePreviews.register({
      id: "molvis:dataset-preview",
      name: "Molvis",
      extensions: [],
      canHandle: ({ hasPreviewSidecar }) => hasPreviewSidecar === true,
      Component: MolvisDatasetPreview,
    });
  },
};

export default molvisPlugin;
