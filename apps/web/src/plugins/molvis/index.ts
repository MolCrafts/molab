import { registerFileTypeContribution } from "@/app/registry";
import { filePreviewPluginRegistry } from "@/lib/file-preview-plugins";
import type { UiPluginModule } from "@/plugins/types";
import { MolvisDatasetPreview } from "./MolvisDatasetPreview";
import { MolvisTab } from "./MolvisTab";
import { isMolvisOpenable } from "./openable";

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
