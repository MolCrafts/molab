import type { PluginAPI, PluginComponent } from "@molcrafts/molexp-plugin";
import { AgentSessionInspector } from "@/app/renderers/AgentSessionInspector";
import { AgentViewer } from "@/app/renderers/AgentViewer";
import { AssetViewer } from "@/app/renderers/AssetViewer";
import { ExperimentViewer } from "@/app/renderers/ExperimentViewer";
import { ImageViewer } from "@/app/renderers/ImageViewer";
import { MetadataInspector } from "@/app/renderers/MetadataInspector";
import { ProjectViewer } from "@/app/renderers/ProjectViewer";
import { RunViewer } from "@/app/renderers/RunViewer";
import { TaskViewer } from "@/app/renderers/TaskViewer";
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

  editor("project", "json", "metadata", "viewer", "Project Overview", ProjectViewer);
  editor("experiment", "json", "metadata", "viewer", "Experiment Overview", ExperimentViewer);
  editor("run", "json", "metadata", "viewer", "Run Overview", RunViewer);
  editor("asset", "json", "metadata", "viewer", "Asset Overview", AssetViewer);
  editor("workspace-file", "image", "image", "viewer", "Image Preview", ImageViewer);
  editor("agent", "json", "metadata", "viewer", "Agent Task", AgentViewer);
  editor("task", "json", "metadata", "viewer", "Task Overview", TaskViewer);

  inspector("project", "json", "metadata", "inspector", "Project Inspector", MetadataInspector);
  inspector(
    "experiment",
    "json",
    "metadata",
    "inspector",
    "Experiment Inspector",
    MetadataInspector,
  );
  inspector("run", "json", "metadata", "inspector", "Run Inspector", MetadataInspector);
  inspector("asset", "json", "metadata", "inspector", "Asset Inspector", MetadataInspector);
  inspector(
    "agent",
    "json",
    "metadata",
    "inspector",
    "Agent Task Inspector",
    AgentSessionInspector,
  );
  inspector("task", "json", "metadata", "inspector", "Task Inspector", TaskViewer);

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
      MetadataInspector,
    );
  }
};
