import { lazy } from "react";
import { buildRegistryKey, registerRendererContribution } from "@/app/registry";
import type { FileKind } from "@/app/types";
import type { UiPluginModule } from "@/plugins/types";

const TextEditor = lazy(() =>
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

const editorPlugin: UiPluginModule = {
  id: "editor",
  name: "Editor",
  description: "Text editor and file preview host for workspace files.",
  userToggleable: true,
  register: () => {
    for (const fileKind of EDITOR_FILE_KINDS) {
      const key = {
        objectType: "workspace-file" as const,
        fileKind,
        contentType: "text" as const,
        panelKind: "editor" as const,
      };
      registerRendererContribution({
        id: `editor:default:${buildRegistryKey(key)}`,
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
