import { lazy } from "react";
import { registerRendererContribution } from "@/app/registry";
import type { UiPluginModule } from "@/plugins/types";

const KnowledgeDocPanel = lazy(() =>
  import("./KnowledgeDocPanel").then((module) => ({ default: module.KnowledgeDocPanel })),
);
const KnowledgeViewer = lazy(() =>
  import("./KnowledgeViewer").then((module) => ({ default: module.KnowledgeViewer })),
);

const knowledgePlugin: UiPluginModule = {
  id: "knowledge",
  name: "Knowledge",
  description: "Notes and literature browser with Milkdown editing.",
  userToggleable: true,
  register: () => {
    registerRendererContribution({
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
    registerRendererContribution({
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
