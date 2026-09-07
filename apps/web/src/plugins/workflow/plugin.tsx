import type { MolexpPluginModule, PluginAPI } from "@molcrafts/molexp-plugin";
import { lazy } from "react";
import { buildRendererRegistryKey } from "@/lib/contribution-types";

const WorkflowFileViewer = lazy(() =>
  import("./WorkflowFileViewer").then((module) => ({ default: module.WorkflowFileViewer })),
);
const WorkflowInspector = lazy(() =>
  import("./WorkflowInspector").then((module) => ({ default: module.WorkflowInspector })),
);
const WorkflowViewer = lazy(() =>
  import("./WorkflowViewer").then((module) => ({ default: module.WorkflowViewer })),
);

const workflowPlugin: MolexpPluginModule = {
  id: "workflow",
  name: "Workflow",
  version: "1.0.0",
  description: "Workflow graph viewer, source tab, and right-rail inspector.",
  activate: (api: PluginAPI) => {
    api.editors.register({
      id: "workflow:viewer",
      key: {
        objectType: "workflow",
        fileKind: "yaml",
        contentType: "metadata",
        panelKind: "viewer",
      },
      title: "Workflow Overview",
      panelSlot: "center",
      priority: 0,
      Component: WorkflowViewer,
    });

    api.inspectors.register({
      id: "workflow:inspector",
      key: {
        objectType: "workflow",
        fileKind: "yaml",
        contentType: "metadata",
        panelKind: "inspector",
      },
      title: "Workflow Inspector",
      panelSlot: "right",
      priority: 0,
      Component: WorkflowInspector,
    });

    const fileKey = {
      objectType: "workspace-file" as const,
      fileKind: "json" as const,
      contentType: "workflow-graph" as const,
      panelKind: "viewer" as const,
    };
    api.editors.register({
      id: `workflow:file:${buildRendererRegistryKey(fileKey)}`,
      key: fileKey,
      title: "Workflow Preview",
      panelSlot: "center",
      priority: 0,
      Component: WorkflowFileViewer,
    });
  },
};

export default workflowPlugin;
