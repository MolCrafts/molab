import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { Atom } from "lucide-react";
import { lazyWithPrefetch } from "@/lib/lazy-with-prefetch";
import {
  BINARY_TRAJECTORY_EXTENSIONS,
  CHEMICAL_STRUCTURE_EXTENSIONS,
  isBinaryTrajectoryName,
  LAMMPS_DATA_EXTENSIONS,
} from "@/lib/structure-files";
import { isMolvisZarr, MOLVIS_FILE_PATTERNS, uniqueMolvisFiles } from "./openable";

const MolvisDatasetPreview = lazyWithPrefetch(() =>
  import("./MolvisDatasetPreview").then((module) => ({
    default: module.MolvisDatasetPreview,
  })),
);
const MolvisRunView = lazyWithPrefetch(() =>
  import("./MolvisRunView").then((module) => ({ default: module.MolvisRunView })),
);
const StructurePreview = lazyWithPrefetch(() =>
  import("./StructurePreview").then((module) => ({ default: module.StructurePreview })),
);

const molvisPlugin: MolabPluginModule = {
  id: "molvis",
  name: "MolVis",
  version: "1.0.0",
  description: "3D scenes for PDB, XYZ, MOL2, SDF and trajectories, plus a *.mrec store.",
  activate: (api: PluginAPI) => {
    api.runViews.register({
      id: "molvis",
      label: "MolVis",
      icon: Atom,
      order: 20,
      files: {
        patterns: [...MOLVIS_FILE_PATTERNS],
        matches: (file) => isMolvisZarr({ name: file.name, relPath: file.relPath }),
      },
      // A `*.mrec` store is one structure, however many markers it lists.
      count: (_, files) => uniqueMolvisFiles(files).length,
      Component: MolvisRunView,
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
      extensions: [
        ...CHEMICAL_STRUCTURE_EXTENSIONS,
        ...LAMMPS_DATA_EXTENSIONS,
        ...BINARY_TRAJECTORY_EXTENSIONS,
      ],
      priority: 20,
      payload: ({ name }) => (isBinaryTrajectoryName(name) ? "bytes" : "text"),
      whole: true,
      Component: StructurePreview,
    });
  },
};

export default molvisPlugin;
