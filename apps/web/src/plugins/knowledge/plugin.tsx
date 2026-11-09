import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { lazyWithPrefetch } from "@/lib/lazy-with-prefetch";
import { registerKnowledgeNavigation } from "./navigation";

const KnowledgeViewer = lazyWithPrefetch(() =>
  import("./KnowledgeViewer").then((module) => ({ default: module.KnowledgeViewer })),
);

const knowledgePlugin: MolabPluginModule = {
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
  },
};

export default knowledgePlugin;
