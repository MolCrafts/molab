import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { registerDefaultRenderers } from "@/app/renderers/registerRenderers";
import { WorkflowPreview } from "@/components/previews/WorkflowPreview";
import { lazyWithPrefetch } from "@/lib/lazy-with-prefetch";
import { getHostActions } from "@/plugins/host_actions";
import { registerCoreNavigation } from "./navigation";

const MarkdownPreview = lazyWithPrefetch(() =>
  import("@/components/previews/MarkdownPreview").then((module) => ({
    default: module.MarkdownPreview,
  })),
);

const corePlugin: MolabPluginModule = {
  id: "core",
  name: "Core",
  version: "1.0.0",
  description: "Built-in project, experiment, and run surfaces.",
  userToggleable: false,
  activate: (api: PluginAPI) => {
    registerCoreNavigation(api);
    registerDefaultRenderers(api);

    api.filePreviews.register({
      id: "core:markdown-preview",
      name: "Markdown Preview",
      extensions: [".md", ".markdown"],
      priority: 20,
      Component: MarkdownPreview,
    });

    api.filePreviews.register({
      id: "core:workflow-preview",
      name: "Workflow Preview",
      extensions: [],
      priority: 30,
      canHandle: ({ name, path }) => {
        const candidate = `${name} ${path}`.toLowerCase();
        return candidate.includes("workflow.");
      },
      Component: WorkflowPreview,
    });

    api.commands.register("reload-window", () => getHostActions().reloadWindow(), {
      title: "Reload Window",
      category: "View",
    });
    api.commands.register("reload-active", () => getHostActions().reloadActiveView(), {
      title: "Reload Active View",
      category: "View",
    });
    api.commands.register("reconnect-remote", () => getHostActions().reconnectRemote(), {
      title: "Reconnect Remote",
      category: "View",
      isVisible: () => getHostActions().isRemote(),
    });
  },
};

export default corePlugin;
