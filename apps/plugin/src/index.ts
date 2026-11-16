/**
 * `@molcrafts/molab-plugin` — authoring SDK for Molab workbench plugins.
 *
 *   import { MolabPlugin, pluginExternals } from "@molcrafts/molab-plugin";
 *   import { Button } from "@molcrafts/molab-plugin/ui";
 */

export type * from "./contract";
export { namespacePluginId } from "./contract";
export {
  PLUGIN_HOST_MODULE_IDS,
  type PluginHostModuleId,
  pluginExternals,
} from "./externals";
export { MolabPlugin } from "./MolabPlugin";
export { cn } from "./utils";
