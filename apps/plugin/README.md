# `@molcrafts/molab-plugin`

Authoring SDK for Molab workbench plugins. Copy of the MolVis plugin
**pattern** (domain `PluginAPI`, namespaced ids, host-injected externals) —
not a shared UI package.

```ts
import { MolabPlugin, type PluginAPI } from "@molcrafts/molab-plugin";
import { pluginExternals } from "@molcrafts/molab-plugin/externals";

export default class Greeter extends MolabPlugin {
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
