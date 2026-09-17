import type { PluginAPI, PluginComponent } from "@molcrafts/molab-plugin";
import {
  AgentSessionInspectorLazy,
  AgentViewerLazy,
  AssetViewerLazy,
  ExperimentViewerLazy,
  ImageViewerLazy,
  MetadataInspectorLazy,
  ProjectViewerLazy,
  RunViewerLazy,
  TaskViewerLazy,
} from "@/app/renderers/lazyRenderers";
import type { FileKind } from "@/app/types";

const rendererId = (
  objectType: string,
  fileKind: string,
  contentType: string,
  panelKind: string,
): string => `exact:${objectType}::${fileKind}::${contentType}::${panelKind}`;

export const registerDefaultRenderers = (api: PluginAPI): void => {
  const editor = (
    objectType: string,
    fileKind: string,
    contentType: string,
    panelKind: string,
    title: string,
    Component: PluginComponent,
  ): void => {
    api.editors.register({
      id: rendererId(objectType, fileKind, contentType, panelKind),
      key: { objectType, fileKind, contentType, panelKind },
      title,
      panelSlot: "center",
      Component,
    });
  };

  const inspector = (
    objectType: string,
    fileKind: string,
    contentType: string,
    panelKind: string,
    title: string,
    Component: PluginComponent,
  ): void => {
    api.inspectors.register({
      id: rendererId(objectType, fileKind, contentType, panelKind),
      key: { objectType, fileKind, contentType, panelKind },
      title,
      panelSlot: "right",
      Component,
    });
  };

  editor("project", "json", "metadata", "viewer", "Project Overview", ProjectViewerLazy);
  editor("experiment", "json", "metadata", "viewer", "Experiment Overview", ExperimentViewerLazy);
  editor("run", "json", "metadata", "viewer", "Run Overview", RunViewerLazy);
  editor("asset", "json", "metadata", "viewer", "Asset Overview", AssetViewerLazy);
  editor("workspace-file", "image", "image", "viewer", "Image Preview", ImageViewerLazy);
  editor("agent", "json", "metadata", "viewer", "Agent Task", AgentViewerLazy);
  editor("task", "json", "metadata", "viewer", "Task Overview", TaskViewerLazy);

  inspector("project", "json", "metadata", "inspector", "Project Inspector", MetadataInspectorLazy);
  inspector(
    "experiment",
    "json",
    "metadata",
    "inspector",
    "Experiment Inspector",
    MetadataInspectorLazy,
  );
  inspector("run", "json", "metadata", "inspector", "Run Inspector", MetadataInspectorLazy);
  inspector("asset", "json", "metadata", "inspector", "Asset Inspector", MetadataInspectorLazy);
  inspector(
    "agent",
    "json",
    "metadata",
    "inspector",
    "Agent Task Inspector",
    AgentSessionInspectorLazy,
  );
  inspector("task", "json", "metadata", "inspector", "Task Inspector", TaskViewerLazy);

  const workspaceFileKinds: readonly FileKind[] = [
    "yaml",
    "json",
    "python",
    "markdown",
    "text",
    "unknown",
    "image",
  ];
  for (const fileKind of workspaceFileKinds) {
    inspector(
      "workspace-file",
      fileKind,
      "metadata",
      "inspector",
      "File Inspector",
      MetadataInspectorLazy,
    );
  }
};
