/**
 * Stable contracts for Molab workbench plugins.
 *
 * Public surface: import from `@molcrafts/molab-plugin`.
 *
 * Contribution surface is **domain-oriented** — there is no free-floating
 * `api.ui` bag. VS Code `contributes.*` names map onto molab host slots.
 *
 * New workbench surfaces (commands, panels, statusBar, settings) are
 * namespaced by the host as `plugin.<pluginId>.<id>`. Existing contribution
 * ids (`molplot:run-tab`, renderer ids, …) stay author-supplied.
 */

import type React from "react";

/**
 * Host renderer / explorer components have slot-specific props. The SDK keeps
 * this generic so plugins can pass concrete components without a circular
 * import of the web app types.
 */
// biome-ignore lint/suspicious/noExplicitAny: host slot props vary; plugins pass concrete components
export type PluginComponent = React.ComponentType<any>;

export type Disposer = () => void;

export interface PluginLogger {
  info(...args: unknown[]): void;
  warn(...args: unknown[]): void;
  error(...args: unknown[]): void;
}

export interface PluginStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** Required repo-root manifest (`manifest.json` in a UI bundle). */
export interface PluginManifest {
  id: string;
  name: string;
  version: string;
  /** ESM entry relative to the package root, e.g. `index.js`. */
  entry: string;
  description?: string;
}

/** Default export shape of a plugin entry module. */
export interface MolabPluginModule {
  id: string;
  name?: string;
  version?: string;
  description?: string;
  /**
   * When false the plugin is always on and hidden from the user toggle list.
   * Defaults to true.
   */
  userToggleable?: boolean;
  activate(api: PluginAPI): void | Promise<void>;
  deactivate?(api: PluginAPI): void | Promise<void>;
  /**
   * @deprecated v1 shim. Prefer `activate(api)`. The host still accepts a
   * `register()`-only default export for one compatibility version.
   */
  register?: () => void | Promise<void>;
}

export type PluginCommandFn<A = unknown, R = unknown> = (args?: A) => R | Promise<R>;

export interface CommandRegisterOptions {
  title?: string;
  category?: string;
  keybinding?: string;
  isVisible?: () => boolean;
}

export type NavigationPlacement = "primary" | "secondary" | "management" | "legacy";
export type NavigationShellMode = "explorer" | "rail-only";

export interface ViewContainerSpec {
  id: string;
  title: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  placement: NavigationPlacement;
  order?: number;
}

export interface ViewSpec {
  id: string;
  container: string;
  title: string;
  breadcrumbLabel?: string;
  route: string;
  shellMode: NavigationShellMode;
  order?: number;
  explorer?: PluginComponent;
  landing?: PluginComponent;
  emptySelection?: { title: string; description: string };
  retainSelectionFor: readonly string[];
  matches: (pathname: string) => boolean;
}

export interface RendererKeySpec {
  objectType: string;
  fileKind: string;
  contentType: string;
  panelKind: string;
}

export interface EditorContribution {
  id: string;
  key: RendererKeySpec;
  title: string;
  panelSlot?: "center" | "right";
  pluginId?: string;
  priority?: number;
  matches?: (context: Record<string, unknown>) => boolean;
  Component: PluginComponent;
}

export type InspectorContribution = EditorContribution;

export type PluginPanelPosition = "bottom";

export interface PluginPanelSpec {
  id: string;
  position: PluginPanelPosition;
  title: string;
  order?: number;
  defaultOpen?: boolean;
  /** Initial height ratio 0–1 when expanded. */
  defaultSize?: number;
  render: React.FC;
}

export interface StatusBarItemSpec {
  id: string;
  text: string;
  tooltip?: string;
  command?: string;
  alignment?: "left" | "right";
  order?: number;
}

export interface SettingsSectionSpec {
  id: string;
  title: string;
  group?: string;
  order?: number;
  render: React.FC;
}

export interface FileMatchContext {
  name: string;
  relPath: string;
  size?: number | null;
  type: string;
  hasPreviewSidecar?: boolean;
}

export interface FileTypeMatcher {
  patterns?: string[];
  matches?: (file: FileMatchContext) => boolean;
}

export interface RunTabBadgeContext {
  projectId: string;
  experimentId: string;
  runId: string;
  executionId: string;
}

export interface FileTypeContribution {
  id: string;
  objectType: string;
  value: string;
  label: string;
  Icon?: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  pluginId?: string;
  priority?: number;
  matcher: FileTypeMatcher;
  Component: PluginComponent;
  resolveTabBadgeCount?: (ctx: RunTabBadgeContext) => Promise<number | null>;
}

/**
 * The run's attempt a run view shows (L14). The host chooses it (the run page's
 * attempt, `?attempt=eNN`, the latest when absent); a run view never does.
 */
export interface RunAttempt {
  projectId: string;
  experimentId: string;
  runId: string;
  /** Run-local attempt id, e.g. `e03`. */
  executionId: string;
  /** The attempt's status (`succeeded`, `running`, `failed`, …). */
  status: string;
  /** The newest attempt of the run. */
  isLatest: boolean;
  /** The latest sealed success — the run's result. */
  isRunResult: boolean;
  /** Workspace-relative attempt directory, as the server reported it. */
  dir: string | null;
}

/** One file of the attempt, relative to `RunAttempt.dir`. */
export type AttemptFile = FileMatchContext;

/** What every run view receives. */
export interface RunViewProps {
  attempt: RunAttempt;
  /** The attempt's files this view matched (`RunViewContribution.files`). */
  files: readonly AttemptFile[];
}

/**
 * A view on the run page (L14), after the core views. Its tab is `label` (a
 * word, R1) with an optional count badge; it exists for an attempt when that
 * attempt has a file `files` matches (no `files`: always). The component
 * renders inside `<RunView>` from `@molcrafts/molab-plugin/ui`.
 */
export interface RunViewContribution {
  id: string;
  label: string;
  /** The phone bottom bar's icon (R2: icon on a phone, the word on a desktop). */
  icon?: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  pluginId?: string;
  /** Tab order after the core views (lower first). */
  order?: number;
  files?: FileTypeMatcher;
  /** The tab's count badge; null for none. */
  count?: (
    attempt: RunAttempt,
    files: readonly AttemptFile[],
  ) => number | null | Promise<number | null>;
  Component: React.ComponentType<RunViewProps>;
}

/** Result of a host file read inside a run view. */
export interface AttemptRead<T> {
  data: T | undefined;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Host services a run view reaches through the `@molcrafts/molab-plugin/ui`
 * hooks (`useAttemptText`, `useAttemptBlob`, `useRunLinks`). Reads are cached
 * per attempt by the host; a view never composes a workspace path.
 */
export interface RunViewHost {
  attempt: RunAttempt;
  /** A hook: the text of an attempt-relative file. */
  useAttemptText: (path: string | null) => AttemptRead<string>;
  /** A hook: an object URL for an attempt-relative file. */
  useAttemptBlob: (path: string | null) => AttemptRead<string>;
  /** Open an attempt-relative file in the editor. */
  openFile: (path: string) => void;
  /** Open the run's Logs view (at a line). */
  openLogs: (line?: number) => void;
}

export interface EntityTabContribution {
  id: string;
  objectType: string;
  value: string;
  label: string;
  Icon?: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  pluginId?: string;
  priority?: number;
  matches?: (context: Record<string, unknown>) => boolean;
  Component: PluginComponent;
}

export interface FilePreviewContentProps {
  content: string;
  name: string;
  path: string;
  folderId: string;
  assetId?: string;
}

export interface FilePreviewContribution {
  id: string;
  name: string;
  extensions: string[];
  pluginId?: string;
  priority?: number;
  canHandle?: (props: { name: string; path: string; hasPreviewSidecar?: boolean }) => boolean;
  Component: React.ComponentType<FilePreviewContentProps>;
}

export interface ExecutionRowData {
  executionId: string;
  runId: string;
  status: string;
  startedAt: string;
  finishedAt: string | null;
  durationSeconds: number | null;
  schedulerJobId: string | null;
  backend: string | null;
  metadata: Record<string, string>;
}

export interface ExecutionColumnContribution {
  id: string;
  pluginId?: string;
  backend?: string;
  columnId: string;
  header: string;
  priority?: number;
  width?: number;
  align?: "left" | "right" | "center";
  Cell: React.ComponentType<{ execution: ExecutionRowData }>;
}

export interface ExecutionDetailContribution {
  id: string;
  pluginId?: string;
  backend?: string;
  title: string;
  priority?: number;
  Component: React.ComponentType<{ execution: ExecutionRowData; runId: string }>;
}

/**
 * Namespace every *new* workbench contribution id under `plugin.<pluginId>.`.
 * Do not pre-namespace ids yourself. Do not treat dotted ids as already
 * namespaced (two plugins both registering `settings.about` must not collide).
 */
export function namespacePluginId(pluginId: string, id: string): string {
  return `plugin.${pluginId}.${id}`;
}

/**
 * Facade handed to every plugin. All `register*` calls are reversed on
 * deactivate / disable / unload.
 *
 * ## Domains
 *
 * | Domain | Host slot |
 * |--------|-----------|
 * | `commands` | command palette ⌘⇧P |
 * | `views` | activity bar + left explorer |
 * | `editors` | center work surface |
 * | `inspectors` | right rail |
 * | `panels` | bottom drawer (v1) |
 * | `statusBar` | 28px status strip |
 * | `settings` | Settings sections |
 * | `runViews` | run page views (L14): `<RunView>` files · view · style |
 * | `fileTypes` | filename tabs of non-run objects |
 * | `entityTabs` | entity tabs of non-run objects |
 * | `execution` | execution table columns / details |
 * | `filePreviews` | editor Preview tab |
 */
export interface PluginAPI {
  readonly pluginId: string;
  readonly log: PluginLogger;
  readonly storage: PluginStorage;

  commands: {
    register<A = unknown, R = unknown>(
      id: string,
      fn: PluginCommandFn<A, R>,
      options?: CommandRegisterOptions,
    ): void;
  };

  views: {
    registerContainer(spec: ViewContainerSpec): void;
    register(spec: ViewSpec): void;
  };

  editors: {
    register(spec: EditorContribution): void;
  };

  inspectors: {
    register(spec: InspectorContribution): void;
  };

  panels: {
    register(spec: PluginPanelSpec): void;
  };

  statusBar: {
    register(spec: StatusBarItemSpec): void;
  };

  settings: {
    registerSection(spec: SettingsSectionSpec): void;
  };

  runViews: {
    register(spec: RunViewContribution): void;
  };

  fileTypes: {
    register(spec: FileTypeContribution): void;
  };

  entityTabs: {
    register(spec: EntityTabContribution): void;
  };

  execution: {
    registerColumn(spec: ExecutionColumnContribution): void;
    registerDetail(spec: ExecutionDetailContribution): void;
  };

  filePreviews: {
    register(spec: FilePreviewContribution): void;
  };
}
