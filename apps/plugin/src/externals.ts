/**
 * Host modules every page plugin must externalize at build time.
 *
 * The host loader injects the same bare specifiers. Both directions fail:
 * - externalized but not injected → bare specifier fails at runtime
 * - injected but not externalized → second copy of React
 *
 * The host's inject map is checked against this list at compile time
 * (`apps/web/src/plugins/host_shared.ts`).
 */

export const PLUGIN_HOST_MODULE_IDS = [
  "react",
  "react-dom",
  "react-dom/client",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "@molcrafts/molab-plugin",
  "@molcrafts/molab-plugin/ui",
] as const;

export type PluginHostModuleId = (typeof PLUGIN_HOST_MODULE_IDS)[number];

/** rspack/rsbuild `externals` map (specifier → specifier). */
export const pluginExternals: Record<PluginHostModuleId, string> = Object.fromEntries(
  PLUGIN_HOST_MODULE_IDS.map((id) => [id, id]),
) as Record<PluginHostModuleId, string>;
