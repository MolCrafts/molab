/**
 * Pure plugin-loader logic for third-party UI bundles.
 *
 * Flow:
 *   1. Fetch ``GET /api/plugins`` — returns a list of `PluginManifest`
 *      descriptors, each carrying the bundle id and two URLs.
 *   2. For each descriptor, fetch its `manifestUrl` and validate the
 *      body against the {@link UiBundleManifest} schema.
 *   3. Skip the bundle (with a warning) when the manifest's
 *      `api_version` does not match the build-time
 *      `UI_PLUGIN_API_VERSION` constant.
 *   4. Resolve the entry URL — `manifest.entry` (default `index.js`)
 *      against the descriptor's `entryUrl` directory — and dynamic-
 *      import it through `state.dynamicImport`.
 *   5. Validate the module's default export shape (`{id, activate}` or
 *      the v1 `{id, register}` shim) and call `activate(api)`.
 *
 * Failures at every step are isolated with `console.warn` so a single
 * broken third-party bundle cannot block other plugins.
 *
 * Kept separate from `runtime.ts` so unit tests can drive the flow
 * without pulling in `corePlugin`'s DOM-bound transitive imports.
 */

import { PluginsService } from "@/api/generated/services/PluginsService";
import { createPluginAPI } from "@/plugins/api/create_api";
import { registerPluginCatalogEntry } from "@/plugins/catalog";
import { runWithPluginContext } from "@/plugins/contribution-runtime";
import type {
  InternalPluginDescriptor,
  PluginManifest,
  UiBundleManifest,
  UiPluginModule,
} from "@/plugins/types";

/**
 * UI-plugin contract version frozen into this build. Each third-party
 * `manifest.json` declares its own `api_version`; the loader skips
 * bundles whose value does not match this constant. Re-exported from
 * `runtime.ts` for backwards-compat callers.
 */
export const UI_PLUGIN_API_VERSION = "1";

export type DynamicImport = (specifier: string) => Promise<unknown>;

export type ManifestFetcher = (url: string) => Promise<UiBundleManifest>;

const defaultDynamicImport: DynamicImport = (specifier) =>
  Function("s", "return import(s)")(specifier);

const defaultFetchManifest: ManifestFetcher = async (url) => {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`fetch ${url} -> HTTP ${response.status}`);
  }
  return (await response.json()) as UiBundleManifest;
};

export type RemoteEntryRewriter = (entryUrl: string) => Promise<string>;

export interface LoaderState {
  installed: Set<string>;
  internalPromises: Map<string, Promise<void>>;
  remotePromises: Map<string, Promise<void>>;
  disposers: Map<string, () => void>;
  dynamicImport: DynamicImport;
  fetchManifest: ManifestFetcher;
  /** Identity by default so unit tests can stub `dynamicImport` against the raw URL. */
  rewriteRemoteEntry: RemoteEntryRewriter;
}

export const createLoaderState = (): LoaderState => ({
  installed: new Set<string>(),
  internalPromises: new Map<string, Promise<void>>(),
  remotePromises: new Map<string, Promise<void>>(),
  disposers: new Map(),
  dynamicImport: defaultDynamicImport,
  fetchManifest: defaultFetchManifest,
  rewriteRemoteEntry: async (url) => url,
});

export const registerInternalPluginDescriptors = (
  descriptors: readonly InternalPluginDescriptor[],
): void => {
  for (const descriptor of descriptors) {
    registerPluginCatalogEntry({
      id: descriptor.id,
      name: descriptor.name,
      description: descriptor.description,
      userToggleable: descriptor.userToggleable,
    });
  }
};

/** Load one bundled plugin exactly once while isolating a broken chunk. */
export const loadInternalPlugin = (
  state: LoaderState,
  descriptor: InternalPluginDescriptor,
): Promise<void> => {
  if (state.installed.has(descriptor.id)) {
    return Promise.resolve();
  }
  const cached = state.internalPromises.get(descriptor.id);
  if (cached) {
    return cached;
  }

  const promise = descriptor
    .load()
    .then((module) => {
      const plugin = pluginFromModule(module);
      if (!plugin || plugin.id !== descriptor.id) {
        console.warn(
          `[plugins] internal plugin "${descriptor.id}" did not export the matching UiPluginModule`,
        );
        return;
      }
      registerPluginInstance(state, plugin);
    })
    .catch((error) => {
      console.warn(`[plugins] failed to load internal plugin "${descriptor.id}":`, error);
      state.internalPromises.delete(descriptor.id);
    });

  state.internalPromises.set(descriptor.id, promise);
  return promise;
};

export const registerPluginInstance = (state: LoaderState, plugin: UiPluginModule): void => {
  if (state.installed.has(plugin.id)) {
    return;
  }
  state.installed.add(plugin.id);

  registerPluginCatalogEntry({
    id: plugin.id,
    name: plugin.name ?? plugin.id,
    description: plugin.description,
    userToggleable: plugin.userToggleable ?? true,
  });

  const { api, disposeAll } = createPluginAPI(plugin.id);
  state.disposers.set(plugin.id, () => {
    try {
      void plugin.deactivate?.(api);
    } catch (error) {
      console.warn(`[plugins] "${plugin.id}" deactivate() threw:`, error);
    }
    disposeAll();
  });

  try {
    const result = runWithPluginContext(plugin.id, () => {
      if (plugin.activate) {
        return plugin.activate(api);
      }
      if (plugin.register) {
        return plugin.register();
      }
      console.warn(`[plugins] "${plugin.id}" has neither activate() nor register()`);
    });
    if (result instanceof Promise) {
      result.catch((error) => {
        console.warn(`[plugins] "${plugin.id}" activate() rejected:`, error);
      });
    }
  } catch (error) {
    console.warn(`[plugins] "${plugin.id}" activate() threw:`, error);
  }
};

export const disposePluginInstance = (state: LoaderState, pluginId: string): void => {
  const dispose = state.disposers.get(pluginId);
  if (!dispose) return;
  dispose();
  state.disposers.delete(pluginId);
  state.installed.delete(pluginId);
};

const looksLikeUiBundleManifest = (mod: unknown): mod is UiBundleManifest => {
  if (!mod || typeof mod !== "object") {
    return false;
  }
  const m = mod as Record<string, unknown>;
  return (
    typeof m.id === "string" &&
    typeof m.name === "string" &&
    typeof m.version === "string" &&
    typeof m.api_version === "string"
  );
};

const hasPluginShape = (value: unknown): value is UiPluginModule => {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as { id?: unknown; activate?: unknown; register?: unknown };
  if (typeof candidate.id !== "string") {
    return false;
  }
  return typeof candidate.activate === "function" || typeof candidate.register === "function";
};

const coercePluginModule = (exported: unknown): UiPluginModule | null => {
  if (typeof exported === "function") {
    const callable = exported as unknown as {
      (): unknown;
      new (): unknown;
    };
    let produced: unknown;
    try {
      produced = new callable();
    } catch {
      try {
        produced = callable();
      } catch {
        return null;
      }
    }
    return coercePluginModule(produced);
  }
  return hasPluginShape(exported) ? exported : null;
};

const pluginFromModule = (mod: unknown): UiPluginModule | null => {
  if (!mod || typeof mod !== "object") {
    return null;
  }
  const candidate = (mod as { default?: unknown }).default ?? mod;
  return coercePluginModule(candidate);
};

const resolveEntryUrl = (descriptor: PluginManifest, manifest: UiBundleManifest): string => {
  const entry = manifest.entry;
  if (!entry || entry === "index.js") {
    return descriptor.entryUrl;
  }
  // Resolve `entry` relative to the bundle's directory — that is, the
  // directory containing `descriptor.entryUrl`. We don't use the URL
  // constructor because relative resolution against a relative URL
  // requires a base; a string slice is unambiguous and bundler-safe.
  const lastSlash = descriptor.entryUrl.lastIndexOf("/");
  const dir = lastSlash >= 0 ? descriptor.entryUrl.slice(0, lastSlash + 1) : "";
  return `${dir}${entry}`;
};

export const loadRemotePlugin = (state: LoaderState, descriptor: PluginManifest): Promise<void> => {
  const cached = state.remotePromises.get(descriptor.id);
  if (cached) {
    return cached;
  }
  const promise = (async () => {
    let manifest: UiBundleManifest;
    try {
      const body = await state.fetchManifest(descriptor.manifestUrl);
      if (!looksLikeUiBundleManifest(body)) {
        console.warn(
          `[plugins] manifest at ${descriptor.manifestUrl} did not match UiBundleManifest schema; skipping ${descriptor.id}`,
        );
        return;
      }
      manifest = body;
    } catch (error) {
      console.warn(`[plugins] failed to fetch manifest for "${descriptor.id}":`, error);
      state.remotePromises.delete(descriptor.id);
      return;
    }

    if (manifest.api_version !== UI_PLUGIN_API_VERSION) {
      console.warn(
        `[plugins] "${descriptor.id}" targets api_version=${manifest.api_version} but UI build expects ${UI_PLUGIN_API_VERSION}; skipping`,
      );
      return;
    }

    const entryUrl = resolveEntryUrl(descriptor, manifest);
    try {
      const specifier = await state.rewriteRemoteEntry(entryUrl);
      const mod = await state.dynamicImport(specifier);
      const plugin = pluginFromModule(mod);
      if (!plugin) {
        console.warn(
          `[plugins] remote plugin "${descriptor.id}" loaded from ${entryUrl} did not export a UiPluginModule`,
        );
        return;
      }
      registerPluginInstance(state, plugin);
    } catch (error) {
      console.warn(
        `[plugins] failed to load remote plugin "${descriptor.id}" from ${entryUrl}:`,
        error,
      );
      state.remotePromises.delete(descriptor.id);
    }
  })();
  state.remotePromises.set(descriptor.id, promise);
  return promise;
};

/**
 * Fetch `/api/plugins` and dispatch each descriptor through
 * {@link loadRemotePlugin}. Failures are isolated.
 */
export const discoverAndLoad = async (state: LoaderState): Promise<void> => {
  let listing: Awaited<ReturnType<typeof PluginsService.listPlugins>>;
  try {
    listing = await PluginsService.listPlugins();
  } catch (error) {
    console.warn("[plugins] /api/plugins fetch failed:", error);
    return;
  }
  await Promise.all(listing.plugins.map((descriptor) => loadRemotePlugin(state, descriptor)));
};

export const resetLoaderState = (state: LoaderState): void => {
  for (const dispose of state.disposers.values()) {
    try {
      dispose();
    } catch {
      /* isolate */
    }
  }
  state.disposers.clear();
  state.installed.clear();
  state.internalPromises.clear();
  state.remotePromises.clear();
  state.dynamicImport = defaultDynamicImport;
  state.fetchManifest = defaultFetchManifest;
  state.rewriteRemoteEntry = async (url) => url;
};
