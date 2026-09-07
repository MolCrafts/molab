import type { InternalPluginDescriptor } from "@/plugins/types";

/**
 * Built-in plugin catalog. Keep this file metadata-only: implementation edges
 * must remain literal dynamic imports so Rsbuild can isolate each capability.
 */
export const INTERNAL_PLUGIN_DESCRIPTORS: readonly InternalPluginDescriptor[] = [
  {
    id: "core",
    name: "Core",
    description: "Built-in project, experiment, and run surfaces.",
    userToggleable: false,
    load: () => import("@/plugins/core"),
  },
  {
    id: "editor",
    name: "Editor",
    description: "Text editor and file preview host for workspace files.",
    userToggleable: true,
    load: () => import("@/plugins/editor/plugin"),
  },
  {
    id: "workflow",
    name: "Workflow",
    description: "Workflow graph viewer, source tab, and right-rail inspector.",
    userToggleable: true,
    load: () => import("@/plugins/workflow/plugin"),
  },
  {
    id: "knowledge",
    name: "Knowledge",
    description: "Notes and literature browser with Milkdown editing.",
    userToggleable: true,
    load: () => import("@/plugins/knowledge/plugin"),
  },
  {
    id: "deltaf",
    name: "ΔF",
    description: "Force-deviation (ΔF) chart tab for phase-1 quantization runs.",
    userToggleable: true,
    load: () => import("@/plugins/deltaf/plugin"),
  },
  {
    id: "molplot",
    name: "MolPlot",
    description: "Metrics and plot tabs for any format a reader contributes.",
    userToggleable: true,
    load: () => import("@/plugins/molplot/plugin"),
  },
  {
    id: "molrs",
    name: "MolRS formats",
    description:
      "Reads solver logs and metric files in the browser via WASM, for whoever is drawing.",
    // Not user-toggleable: disabling it would silently empty every chart
    // rather than remove a visible surface.
    userToggleable: false,
    load: () => import("@/plugins/molrs/plugin"),
  },
  {
    id: "molq",
    name: "Molq",
    description: "Scheduler run monitor, Molq tab, and execution columns for molq backends.",
    userToggleable: true,
    load: () => import("@/plugins/molq/plugin"),
  },
  {
    id: "molvis",
    name: "MolVis",
    description:
      "Trajectory and structure viewer tab when a run has PDB/XYZ/LAMMPS dumps or a *.mrec store.",
    userToggleable: true,
    load: () => import("@/plugins/molvis/plugin"),
  },
  {
    id: "tensorboard",
    name: "TensorBoard",
    description: "TensorBoard tab when tfevents files are discovered on a run.",
    userToggleable: true,
    load: () => import("@/plugins/tensorboard/plugin"),
  },
];

export const getInternalPluginDescriptor = (id: string): InternalPluginDescriptor | undefined =>
  INTERNAL_PLUGIN_DESCRIPTORS.find((descriptor) => descriptor.id === id);
