import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import type { FileKind } from "@/app/types";
import { buildRendererRegistryKey } from "@/lib/contribution-types";
import { lazyWithPrefetch } from "@/lib/lazy-with-prefetch";

const TextEditor = lazyWithPrefetch(() =>
  import("./TextEditor").then((module) => ({ default: module.TextEditor })),
);

const EDITOR_FILE_KINDS: readonly FileKind[] = [
  "yaml",
  "json",
  "python",
  "markdown",
  "text",
  "unknown",
];

const editorPlugin: MolabPluginModule = {
  id: "editor",
  name: "Editor",
  version: "1.0.0",
  description: "Text editor and file preview host for workspace files.",
  activate: (api: PluginAPI) => {
    for (const fileKind of EDITOR_FILE_KINDS) {
      const key = {
        objectType: "workspace-file" as const,
        fileKind,
        contentType: "text" as const,
        panelKind: "editor" as const,
      };
      api.editors.register({
        id: `editor:default:${buildRendererRegistryKey(key)}`,
        priority: 0,
        key,
        title: "Text Editor",
        panelSlot: "center",
        Component: TextEditor,
      });
    }
  },
};

export default editorPlugin;
