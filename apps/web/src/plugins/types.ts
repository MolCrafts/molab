export type {
  DiscoveredFile,
  EntityTabContribution,
  ExecutionColumnContribution,
  ExecutionColumnRenderProps,
  ExecutionDetailContribution,
  ExecutionDetailRenderProps,
  ExecutionRowData,
  FileMatchContext,
  FilePreviewContentProps,
  FilePreviewPlugin,
  FileTypeContribution,
  FileTypeMatcher,
  PanelSlot,
  RendererContribution,
  RendererEntry,
  RendererResolutionContext,
  RenderTarget,
  RunTabBadgeContext,
} from "@/lib/contribution-types";
export { buildRendererRegistryKey } from "@/lib/contribution-types";

/**
 * One entry returned by ``GET /api/plugins`` — a discovered third-party
 * UI bundle's distribution metadata. Carries no UI semantics: `id` is
 * the entry-point name on the Python side; `manifestUrl` and `entryUrl`
 * point into the bundle's mounted directory. Real UI semantics live in
 * the bundle's ``manifest.json`` (see {@link UiBundleManifest}), fetched
 * by the loader once it sees this descriptor.
 */
export interface PluginManifest {
  id: string;
  manifestUrl: string;
  entryUrl: string;
}

/**
 * Schema of ``manifest.json`` shipped at the root of each third-party
 * UI bundle. The browser-side loader fetches it, validates the shape,
 * and checks ``api_version`` against the
 * ``UI_PLUGIN_API_VERSION`` constant frozen into this build.
 */
export interface UiBundleManifest {
  id: string;
  name: string;
  version: string;
  api_version: "1";
  /** Optional override for the entry filename. Defaults to `index.js`. */
  entry?: string;
  capabilities?: string[];
}

export interface UiPluginModule {
  id: string;
  /** Human-readable name for Settings / catalog. Defaults to `id`. */
  name?: string;
  /** Short description shown under the toggle in Settings. */
  description?: string;
  /**
   * When false the plugin is always on and hidden from the user toggle list.
   * Defaults to true (panel plugins are user-controllable).
   */
  userToggleable?: boolean;
  register: () => void | Promise<void>;
}
