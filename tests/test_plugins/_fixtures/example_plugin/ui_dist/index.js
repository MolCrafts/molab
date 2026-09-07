// Example third-party plugin ESM bundle (test fixture).
//
// A real package externalizes `@molcrafts/molexp-plugin` (see pluginExternals)
// and default-exports `{ id, activate(api) }`. This fixture stays a tiny
// shape-correct stub so Python discovery tests can serve the file.

const RENDERER_MARKER = "molexp-example-plugin-renderer";

const examplePlugin = {
  id: "example",
  activate(api) {
    if (typeof globalThis !== "undefined") {
      globalThis.__molexpExamplePluginRegistered = true;
      globalThis.__molexpExamplePluginMarker = RENDERER_MARKER;
    }
    api?.log?.info?.("example plugin activated");
  },
  // v1 shim — host still accepts register()-only modules.
  register() {
    this.activate();
  },
};

export default examplePlugin;
