import type { PluginAPI, PluginComponent } from "@molcrafts/molab-plugin";
import {
  AssetViewerLazy,
  ExperimentViewerLazy,
  ImageViewerLazy,
  ProjectViewerLazy,
  RunViewerLazy,
  TaskViewerLazy,
} from "@/app/renderers/lazyRenderers";

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

  editor("project", "json", "metadata", "viewer", "Project Overview", ProjectViewerLazy);
  editor("experiment", "json", "metadata", "viewer", "Experiment Overview", ExperimentViewerLazy);
  editor("run", "json", "metadata", "viewer", "Run Overview", RunViewerLazy);
  editor("asset", "json", "metadata", "viewer", "Asset Overview", AssetViewerLazy);
  editor("workspace-file", "image", "image", "viewer", "Image Preview", ImageViewerLazy);
  editor("task", "json", "metadata", "viewer", "Task Overview", TaskViewerLazy);
};
