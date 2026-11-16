import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { lazy } from "react";
import { buildRendererRegistryKey } from "@/lib/contribution-types";

const WorkflowFileViewer = lazy(() =>
  import("./WorkflowFileViewer").then((module) => ({ default: module.WorkflowFileViewer })),
);
const WorkflowViewer = lazy(() =>
  import("./WorkflowViewer").then((module) => ({ default: module.WorkflowViewer })),
);

const workflowPlugin: MolabPluginModule = {
  id: "workflow",
  name: "Workflow",
  version: "1.0.0",
  description: "Workflow graph viewer and source tab.",
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
