import type { PluginStorage } from "@molcrafts/molab-plugin";

export function pluginStorageNamespace(pluginId: string): PluginStorage {
  const prefix = `molab.plugin.${pluginId}.`;
  return {
    getItem(key: string): string | null {
      if (typeof localStorage === "undefined") return null;
      return localStorage.getItem(prefix + key);
    },
    setItem(key: string, value: string): void {
      if (typeof localStorage === "undefined") return;
      localStorage.setItem(prefix + key, value);
    },
    removeItem(key: string): void {
      if (typeof localStorage === "undefined") return;
      localStorage.removeItem(prefix + key);
    },
  };
}
