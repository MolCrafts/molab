/**
 * OOP base for MolExp workbench plugins.
 *
 * Domain registration stays in `activate(api)`. Subclass only owns identity
 * plus activate/deactivate wiring.
 *
 * ```ts
 * import { MolexpPlugin, type PluginAPI } from "@molcrafts/molexp-plugin";
 *
 * export default class MyPlugin extends MolexpPlugin {
 *   readonly id = "com.example.my-plugin";
 *   readonly name = "My Plugin";
 *   readonly version = "0.1.0";
 *   activate(api: PluginAPI) { ... }
 * }
 * ```
 */

import type { MolexpPluginModule, PluginAPI } from "./contract";

export abstract class MolexpPlugin implements MolexpPluginModule {
  abstract readonly id: string;
  abstract readonly name: string;
  abstract readonly version: string;

  abstract activate(api: PluginAPI): void | Promise<void>;

  deactivate(_api: PluginAPI): void | Promise<void> {
    /* default: no-op */
  }
}
