/**
 * OOP base for Molab workbench plugins.
 *
 * Domain registration stays in `activate(api)`. Subclass only owns identity
 * plus activate/deactivate wiring.
 *
 * ```ts
 * import { MolabPlugin, type PluginAPI } from "@molcrafts/molab-plugin";
 *
 * export default class MyPlugin extends MolabPlugin {
 *   readonly id = "com.example.my-plugin";
 *   readonly name = "My Plugin";
 *   readonly version = "0.1.0";
 *   activate(api: PluginAPI) { ... }
 * }
 * ```
 */

import type { MolabPluginModule, PluginAPI } from "./contract";

export abstract class MolabPlugin implements MolabPluginModule {
  abstract readonly id: string;
  abstract readonly name: string;
  abstract readonly version: string;

  abstract activate(api: PluginAPI): void | Promise<void>;

  deactivate(_api: PluginAPI): void | Promise<void> {
    /* default: no-op */
  }
}
