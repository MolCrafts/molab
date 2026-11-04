import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { Atom } from "lucide-react";
import { lazyWithPrefetch } from "@/lib/lazy-with-prefetch";
import { CHEMICAL_STRUCTURE_EXTENSIONS } from "@/lib/structure-files";
import { isMolvisOpenable } from "./openable";

const MolvisDatasetPreview = lazyWithPrefetch(() =>
  import("./MolvisDatasetPreview").then((module) => ({
    default: module.MolvisDatasetPreview,
  })),
);
const MolvisTab = lazyWithPrefetch(() =>
  import("./MolvisTab").then((module) => ({ default: module.MolvisTab })),
);
const StructurePreview = lazyWithPrefetch(() =>
  import("./StructurePreview").then((module) => ({ default: module.StructurePreview })),
);

const molvisPlugin: MolabPluginModule = {
  id: "molvis",
  name: "MolVis",
  version: "1.0.0",
  description:
    "2D formula and 3D model for PDB, XYZ, MOL2, SDF, and trajectories, plus a *.mrec store.",
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

    api.filePreviews.register({
      id: "molvis:structure",
      name: "Structure",
      extensions: [...CHEMICAL_STRUCTURE_EXTENSIONS],
      priority: 20,
      Component: StructurePreview,
    });
  },
};

export default molvisPlugin;
