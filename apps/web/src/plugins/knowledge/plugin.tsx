import type { MolexpPluginModule, PluginAPI } from "@molcrafts/molexp-plugin";
import { lazy } from "react";
import { registerKnowledgeNavigation } from "./navigation";

const KnowledgeDocPanel = lazy(() =>
  import("./KnowledgeDocPanel").then((module) => ({ default: module.KnowledgeDocPanel })),
);
const KnowledgeViewer = lazy(() =>
  import("./KnowledgeViewer").then((module) => ({ default: module.KnowledgeViewer })),
);

const knowledgePlugin: MolexpPluginModule = {
  id: "knowledge",
  name: "Knowledge",
  version: "1.0.0",
  description: "Notes and literature browser with Milkdown editing.",
  activate: (api: PluginAPI) => {
    registerKnowledgeNavigation(api);
    api.editors.register({
      id: "knowledge:viewer",
      key: {
        objectType: "knowledge",
        fileKind: "json",
        contentType: "metadata",
        panelKind: "viewer",
      },
      title: "Knowledge",
      panelSlot: "center",
      priority: 0,
      Component: KnowledgeViewer,
    });
    api.inspectors.register({
      id: "knowledge:inspector",
      key: {
        objectType: "knowledge",
        fileKind: "json",
        contentType: "metadata",
        panelKind: "inspector",
      },
      title: "Document",
      panelSlot: "right",
      priority: 0,
      Component: KnowledgeDocPanel,
    });
  },
};

export default knowledgePlugin;
