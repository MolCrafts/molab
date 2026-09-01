import { Atom } from "lucide-react";
import { lazy } from "react";
import { registerFileTypeContribution } from "@/app/registry";
import { filePreviewPluginRegistry } from "@/lib/file-preview-plugins";
import type { UiPluginModule } from "@/plugins/types";
import { isMolvisOpenable } from "./openable";

const MolvisDatasetPreview = lazy(() =>
  import("./MolvisDatasetPreview").then((module) => ({
    default: module.MolvisDatasetPreview,
  })),
);
const MolvisTab = lazy(() =>
  import("./MolvisTab").then((module) => ({ default: module.MolvisTab })),
);

const molvisPlugin: UiPluginModule = {
  id: "molvis",
  name: "MolVis",
  description:
    "Trajectory and structure viewer tab when a run has PDB/XYZ/LAMMPS dumps or a *.mrec store.",
  userToggleable: true,
  register: () => {
    registerFileTypeContribution({
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

    filePreviewPluginRegistry.register({
      id: "molvis:dataset-preview",
      name: "Molvis",
      extensions: [],
      canHandle: ({ hasPreviewSidecar }) => hasPreviewSidecar === true,
      Component: MolvisDatasetPreview,
    });
  },
};

export default molvisPlugin;
