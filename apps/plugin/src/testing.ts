/**
 * Test double for {@link PluginAPI}.
 *
 * Building the double from the real contract means a new domain shows up as
 * a compile error here rather than silently passing everywhere.
 */

import type { PluginAPI, PluginStorage } from "./contract";

export function mapStorage(backing = new Map<string, string>()): PluginStorage {
  return {
    getItem: (key) => backing.get(key) ?? null,
    setItem: (key, value) => {
      backing.set(key, value);
    },
    removeItem: (key) => {
      backing.delete(key);
    },
  };
}

/**
 * A complete no-op `PluginAPI`. Pass `overrides` to record the calls a test
 * cares about; every other domain stays a silent stub.
 */
export function fakePluginAPI(overrides: Partial<PluginAPI> = {}): PluginAPI {
  return {
    pluginId: "com.example.test",
    log: { info() {}, warn() {}, error() {} },
    storage: mapStorage(),
    commands: { register() {} },
    views: { registerContainer() {}, register() {} },
    editors: { register() {} },
    inspectors: { register() {} },
    panels: { register() {} },
    statusBar: { register() {} },
    settings: { registerSection() {} },
    fileTypes: { register() {} },
    entityTabs: { register() {} },
    execution: { registerColumn() {}, registerDetail() {} },
    filePreviews: { register() {} },
    ...overrides,
  };
}
