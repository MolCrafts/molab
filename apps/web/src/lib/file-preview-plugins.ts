import {
  listFilePreviewContributions,
  registerFilePreviewContribution,
  unregisterFilePreviewContribution,
} from "@/lib/contribution-runtime";
import type { FilePreviewPayload, FilePreviewPlugin } from "@/lib/contribution-types";

export type {
  FilePreviewContentProps,
  FilePreviewPayload,
  FilePreviewPlugin,
} from "@/lib/contribution-types";

/** The load a plugin asked for. Absent means text. */
export const filePreviewPayload = (
  plugin: FilePreviewPlugin,
  file: { name: string; path: string },
): FilePreviewPayload => {
  const payload = plugin.payload;
  if (typeof payload === "function") return payload(file);
  return payload ?? "text";
};

class FilePreviewPluginRegistry {
  register(plugin: FilePreviewPlugin): void {
    registerFilePreviewContribution(plugin);
  }

  unregister(pluginId: string): boolean {
    return unregisterFilePreviewContribution(pluginId);
  }

  getPluginForFile(
    filename: string,
    path?: string,
    opts?: { hasPreviewSidecar?: boolean },
  ): FilePreviewPlugin | null {
    const extension = this.getExtension(filename);

    for (const plugin of listFilePreviewContributions()) {
      if (plugin.extensions.includes(extension)) {
        return plugin;
      }

      if (
        plugin.canHandle?.({
          name: filename,
          path: path ?? filename,
          hasPreviewSidecar: opts?.hasPreviewSidecar,
        })
      ) {
        return plugin;
      }
    }

    return null;
  }

  getAllPlugins(): FilePreviewPlugin[] {
    return listFilePreviewContributions();
  }

  clear(): void {
    for (const plugin of listFilePreviewContributions()) {
      unregisterFilePreviewContribution(plugin.id);
    }
  }

  private getExtension(filename: string): string {
    const lastDot = filename.lastIndexOf(".");
    if (lastDot === -1 || lastDot === 0) {
      return "";
    }
    return filename.slice(lastDot).toLowerCase();
  }
}

export const filePreviewPluginRegistry = new FilePreviewPluginRegistry();
