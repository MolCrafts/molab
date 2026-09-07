import type { PluginStorage } from "@molcrafts/molexp-plugin";

export function pluginStorageNamespace(pluginId: string): PluginStorage {
  const prefix = `molexp.plugin.${pluginId}.`;
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
