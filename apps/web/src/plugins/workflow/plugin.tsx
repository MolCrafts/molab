import { lazy } from "react";
import { buildRegistryKey, registerRendererContribution } from "@/app/registry";
import type { UiPluginModule } from "@/plugins/types";

const WorkflowFileViewer = lazy(() =>
  import("./WorkflowFileViewer").then((module) => ({ default: module.WorkflowFileViewer })),
);
const WorkflowInspector = lazy(() =>
  import("./WorkflowInspector").then((module) => ({ default: module.WorkflowInspector })),
);
const WorkflowViewer = lazy(() =>
  import("./WorkflowViewer").then((module) => ({ default: module.WorkflowViewer })),
);

const workflowPlugin: UiPluginModule = {
  id: "workflow",
  name: "Workflow",
  description: "Workflow graph viewer, source tab, and right-rail inspector.",
  userToggleable: true,
  register: () => {
    registerRendererContribution({
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

    registerRendererContribution({
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
    registerRendererContribution({
      id: `workflow:file:${buildRegistryKey(fileKey)}`,
      key: fileKey,
      title: "Workflow Preview",
      panelSlot: "center",
      priority: 0,
      Component: WorkflowFileViewer,
    });
  },
};

export default workflowPlugin;
