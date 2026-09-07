# `@molcrafts/molexp-plugin`

Authoring SDK for MolExp workbench plugins. Copy of the MolVis plugin
**pattern** (domain `PluginAPI`, namespaced ids, host-injected externals) —
not a shared UI package.

```ts
import { MolexpPlugin, type PluginAPI } from "@molcrafts/molexp-plugin";
import { pluginExternals } from "@molcrafts/molexp-plugin/externals";

export default class Greeter extends MolexpPlugin {
  readonly id = "greeter";
  readonly name = "Greeter";
  readonly version = "0.1.0";
  activate(api: PluginAPI) {
    api.commands.register("hello", () => api.log.info("hello"), {
      title: "Say hello",
    });
  }
}
```

Externalize every id in `PLUGIN_HOST_MODULE_IDS` at bundle time (`pluginExternals`).
The host injects a single React / SDK instance.
