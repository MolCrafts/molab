import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { Network } from "lucide-react";
import { lazyWithPrefetch } from "@/lib/lazy-with-prefetch";
import { registerKnowledgeNavigation } from "./navigation";

const KnowledgeViewer = lazyWithPrefetch(() =>
  import("./KnowledgeViewer").then((module) => ({ default: module.KnowledgeViewer })),
);

const KnowledgeRelations = lazyWithPrefetch(() =>
  import("./KnowledgeRelations").then((module) => ({ default: module.KnowledgeRelations })),
);

const knowledgePlugin: MolabPluginModule = {
  id: "knowledge",
  name: "Knowledge",
  version: "1.0.0",
  description: "Notes and literature browser with Milkdown editing.",
  activate: (api: PluginAPI) => {
    registerKnowledgeNavigation(api);
    api.entityTabs.register({
      id: "knowledge:relations",
      objectType: "project",
      value: "relations",
      label: "Relations",
      Icon: Network,
      Component: KnowledgeRelations,
    });
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
