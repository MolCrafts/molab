import type { MolexpPluginModule, PluginAPI } from "@molcrafts/molexp-plugin";
import { Atom } from "lucide-react";
import { lazy } from "react";
import { isMolvisOpenable } from "./openable";

const MolvisDatasetPreview = lazy(() =>
  import("./MolvisDatasetPreview").then((module) => ({
    default: module.MolvisDatasetPreview,
  })),
);
const MolvisTab = lazy(() =>
  import("./MolvisTab").then((module) => ({ default: module.MolvisTab })),
);

const molvisPlugin: MolexpPluginModule = {
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
