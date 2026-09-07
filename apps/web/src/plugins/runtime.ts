/**
 * Plugin runtime bootstrap.
 *
 * Exposes `bootPlugins()` which `index.tsx` calls **after**
 * `enableMocking()` resolves, so the MSW service worker (in
 * dev:mock mode) is fully in control of the page before the loader
 * issues its first `/api/plugins` fetch. Doing this work as a
 * top-level module side effect would race the service-worker
 * activation: `requestIdleCallback` queues the discovery before SW
 * is ready, the first fetch escapes to the rsbuild proxy, and the
 * loader silently logs a warning instead of finding any plugins.
 *
 * Internal plugins are represented by lightweight descriptors. Core is
 * awaited before the application renders; optional enabled capabilities load
 * concurrently afterwards, and disabled capabilities never enter the startup
 * execution path. They do NOT appear in `/api/plugins`.
 * Third-party bundles discovered through Python's
 * `molexp.ui_plugins` entry-point group are the only consumers of
 * the dynamic-import loader path.
 *
 * Pure logic lives in `./loader.ts` so unit tests can exercise it
 * without dragging in `corePlugin`'s DOM-bound transitive imports.
 */

import { resetPluginCatalogForTests } from "@/plugins/catalog";
import { resetContributionRuntimeForTests } from "@/plugins/contribution-runtime";
import { resetHostActionsForTests } from "@/plugins/host_actions";
import { ensurePluginHostModules, rewriteModuleGraph } from "@/plugins/host_loader";
import { getInternalPluginDescriptor, INTERNAL_PLUGIN_DESCRIPTORS } from "@/plugins/internal";
import {
  createLoaderState,
  type DynamicImport,
  discoverAndLoad,
  type LoaderState,
  loadInternalPlugin,
  loadRemotePlugin,
  type ManifestFetcher,
  registerInternalPluginDescriptors,
  resetLoaderState,
  UI_PLUGIN_API_VERSION,
} from "@/plugins/loader";
import { isPluginEnabled, resetPluginPreferencesForTests } from "@/plugins/preferences";

/**
 * UI-plugin contract version frozen into this build. Defined in
 * `loader.ts` (where it's actually consumed); re-exported here as the
 * public API surface.
 */
export { UI_PLUGIN_API_VERSION };

const state: LoaderState = createLoaderState();
let bootPromise: Promise<void> | null = null;

/**
 * Register built-in metadata, install the core renderers, then start enabled
 * optional capabilities and third-party discovery without delaying first
 * render. Idempotent — calling twice returns the same promise.
 *
 * Must be called from the entry module **after** the application
 * has done any boot-time work that needs to land before plugin
 * discovery fires — most importantly, after `enableMocking()` in
 * dev:mock mode. Otherwise the loader's first fetch will race the
 * service-worker activation and silently fail.
 */
export const bootPlugins = (): Promise<void> => {
  if (bootPromise) {
    return bootPromise;
  }
  registerInternalPluginDescriptors(INTERNAL_PLUGIN_DESCRIPTORS);
  state.rewriteRemoteEntry = async (url) => {
    await ensurePluginHostModules();
    return rewriteModuleGraph(url);
  };
  const core = getInternalPluginDescriptor("core");
  if (!core) {
    throw new Error("Core plugin descriptor is missing");
  }

  bootPromise = loadInternalPlugin(state, core).then(async () => {
    // Knowledge owns a rail view — load it before first paint so `/knowledge`
    // and the activity bar do not flash empty. Other optional plugins stay idle.
    const knowledge = getInternalPluginDescriptor("knowledge");
    if (knowledge && isPluginEnabled(knowledge.id)) {
      await loadInternalPlugin(state, knowledge);
    }

    const loadOptionalPlugins = (): void => {
      for (const descriptor of INTERNAL_PLUGIN_DESCRIPTORS) {
        if (
          descriptor.id !== "core" &&
          descriptor.id !== "knowledge" &&
          isPluginEnabled(descriptor.id)
        ) {
          void loadInternalPlugin(state, descriptor);
        }
      }
      void discoverAndLoad(state);
    };

    if (typeof window === "undefined") {
      return;
    }

    const idle = (
      window as Window & {
        requestIdleCallback?: (cb: () => void) => void;
      }
    ).requestIdleCallback;
    if (idle) {
      idle(loadOptionalPlugins);
    } else {
      setTimeout(loadOptionalPlugins, 0);
    }
  });
  return bootPromise;
};

export const ensureInternalPlugin = (id: string): Promise<void> => {
  const descriptor = getInternalPluginDescriptor(id);
  return descriptor ? loadInternalPlugin(state, descriptor) : Promise.resolve();
};

export const ensureRemotePlugin = (
  id: string,
  manifestUrl: string,
  entryUrl: string,
): Promise<void> => {
  return loadRemotePlugin(state, { id, manifestUrl, entryUrl });
};

export const resetUiPluginsForTests = (): void => {
  resetLoaderState(state);
  resetContributionRuntimeForTests();
  resetPluginCatalogForTests();
  resetPluginPreferencesForTests();
  resetHostActionsForTests();
  bootPromise = null;
};

export const testHooks = {
  setDynamicImport: (impl: DynamicImport) => {
    state.dynamicImport = impl;
  },
  setFetchManifest: (impl: ManifestFetcher) => {
    state.fetchManifest = impl;
  },
  resetDynamicImport: () => {
    resetLoaderState(state);
  },
  discoverAndLoad: () => discoverAndLoad(state),
};
