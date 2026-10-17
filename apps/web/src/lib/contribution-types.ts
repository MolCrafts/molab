import type React from "react";
import type {
  ContentType,
  FileKind,
  PanelKind,
  RendererKey,
  RendererProps,
  RendererSnapshot,
  Selection,
  SemanticObjectType,
} from "@/app/types";

export type PanelSlot = "center" | "right";

export interface RendererEntry {
  key: RendererKey;
  title: string;
  panelSlot: PanelSlot;
  Component: React.ComponentType<RendererProps>;
}

export interface RenderTarget {
  panelKind: PanelKind;
  contentType: ContentType;
  fileKind: FileKind;
}

export interface RendererResolutionContext {
  key: RendererKey;
  selection: Selection;
  snapshot: RendererSnapshot;
  target: RenderTarget;
}

export interface RendererContribution extends RendererEntry {
  id: string;
  /** Owning UI plugin id — stamped at register time for enable/disable. */
  pluginId?: string;
  priority?: number;
  matches?: (context: RendererResolutionContext) => boolean;
}

export interface FilePreviewContentProps {
  content: string;
  name: string;
  path: string;
  folderId: string;
  assetId?: string;
}

export interface FilePreviewPlugin {
  id: string;
  name: string;
  extensions: string[];
  /** Owning UI plugin id — stamped at register time for enable/disable. */
  pluginId?: string;
  priority?: number;
  canHandle?: (props: { name: string; path: string; hasPreviewSidecar?: boolean }) => boolean;
  Component: React.ComponentType<FilePreviewContentProps>;
}

export interface EntityTabContribution {
  id: string;
  objectType: SemanticObjectType;
  value: string;
  label: string;
  /** Optional workbench glyph used by contextual plugin launchers. */
  Icon?: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  /** Owning UI plugin id — stamped at register time for enable/disable. */
  pluginId?: string;
  priority?: number;
  /**
   * Optional gate (e.g. molq backend only). When omitted the tab is always
   * offered for ``objectType``.
   */
  matches?: (context: { selection: Selection; snapshot: RendererSnapshot }) => boolean;
  Component: React.ComponentType<RendererProps>;
}

export interface FileMatchContext {
  name: string;
  relPath: string;
  size?: number | null;
  type: string;
  /**
   * Server-computed signal: the file has a same-stem `.py` preview sidecar
   * (existence-only — no user code was executed to determine it). Lets a
   * contribution light up for datasets that match no extension pattern.
   */
  hasPreviewSidecar?: boolean;
}

export interface FileTypeMatcher {
  patterns?: string[];
  matches?: (file: FileMatchContext) => boolean;
}

export interface DiscoveredFile extends FileMatchContext {
  matchedBy: string;
}

export interface RunTabBadgeContext {
  projectId: string;
  experimentId: string;
  runId: string;
  executionId: string;
}

export interface FileTypeContribution {
  id: string;
  objectType: SemanticObjectType;
  value: string;
  label: string;
  /** Optional workbench glyph used by contextual plugin launchers. */
  Icon?: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  /** Owning UI plugin id — stamped at register time for enable/disable. */
  pluginId?: string;
  priority?: number;
  matcher: FileTypeMatcher;
  Component: React.ComponentType<RendererProps & { discoveredFiles: DiscoveredFile[] }>;
  /**
   * When set, the run tab parenthetical uses this catalog count instead of
   * the matched-file count (e.g. molplot scalar series, not WAL/Zarr files).
   */
  resolveTabBadgeCount?: (ctx: RunTabBadgeContext) => Promise<number | null>;
}

/**
 * Per-execution data passed to plugin renderers.
 *
 * Mirrors `WorkspaceExecutionRow` returned by `/api/workspace/runs`. The
 * `backend` discriminator decides which plugin contribution(s) light up
 * for this row; `metadata` carries scheduler-specific fields (cluster,
 * scheduler_job_id, queue, …) for table cells and detail panels.
 */
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

export interface ExecutionColumnRenderProps {
  execution: ExecutionRowData;
}

export interface ExecutionColumnContribution {
  id: string;
  /** Owning UI plugin id — stamped at register time for enable/disable. */
  pluginId?: string;
  /** Backend discriminator (e.g. "molq"). Undefined = always render. */
  backend?: string;
  /** Stable column key used for header + ordering. */
  columnId: string;
  header: string;
  priority?: number;
  /** Optional fixed pixel width hint for the column header cell. */
  width?: number;
  align?: "left" | "right" | "center";
  Cell: React.ComponentType<ExecutionColumnRenderProps>;
}

export interface ExecutionDetailRenderProps {
  execution: ExecutionRowData;
  /** Parent run id for plugins that need run-level context. */
  runId: string;
}

export interface ExecutionDetailContribution {
  id: string;
  /** Owning UI plugin id — stamped at register time for enable/disable. */
  pluginId?: string;
  backend?: string;
  title: string;
  priority?: number;
  Component: React.ComponentType<ExecutionDetailRenderProps>;
}

export const buildRendererRegistryKey = (key: RendererKey): string => {
  return `${key.objectType}::${key.fileKind}::${key.contentType}::${key.panelKind}`;
};

/**
 * One sample of one series, in the shape a chart consumes.
 *
 * Deliberately the same shape molab's own WAL already uses, so a reader for
 * a foreign format and a reader for the WAL produce interchangeable output
 * and neither is the privileged one.
 */
export interface MetricRecordSample {
  /** Record kind — `"scalar"` today. */
  t: string;
  /** Series key, e.g. `"lammps/Temp"`. */
  k: string;
  /** Simulation step, when the source has one. */
  s?: number;
  /** Wall-clock stamp, when the source actually measured one. */
  w?: string;
  v?: unknown;
  tags?: Record<string, unknown>;
}

/**
 * What a viewer asks a reader for.
 *
 * Sampling is the *viewer's* policy: it knows how many points the chart can
 * show. The reader knows how to skip cheaply, so the request travels down
 * rather than the viewer discarding what was already built.
 */
export interface MetricReadRequest {
  /**
   * Emit at most one sample per this many simulation steps, per series.
   *
   * The viewer states resolution in the data's own units — "a point every
   * 10 000 steps" — not in rows. It cannot state rows: it does not know how
   * many a file has, and a solver's output frequency changes between restart
   * blocks, so every Nth *row* would sample one stretch of the run more
   * densely than another. Every Nth *step* is uniform in simulation time
   * whatever the writing frequency was.
   *
   * A record with no step is not a time series (a one-off scalar like an atom
   * count) and is always kept.
   */
  stepInterval?: number;
  /** Stop after this many records. */
  limit?: number;
  /** Keep only these series keys. Empty or absent means every series. */
  keys?: string[];
}

/**
 * A format some package can turn into plottable records.
 *
 * molplot registers none of these: it displays. A package that owns a format
 * contributes the reader — molrs owns the solver formats and reads them in
 * WASM, so the browser parses the file itself rather than asking a server to
 * convert it first.
 */
export interface MetricReaderContribution {
  id: string;
  /** Stable format id, e.g. `"lammps_log"`. Shown beside the chart. */
  format: string;
  /** Human label for the format picker. */
  label: string;
  /** Owning UI plugin id — stamped at register time for enable/disable. */
  pluginId?: string;
  /** Consulted before lower ones when several readers claim a file. */
  priority?: number;
  /**
   * Glob hints used to offer a chart *without* fetching the file. A hint,
   * never the authority — {@link MetricReaderContribution.claims} decides
   * once the bytes are in hand. Keep them narrow: too broad offers an empty
   * chart on unrelated files, too narrow costs only a tab.
   */
  patterns: string[];
  /** True when the file grows while a run is live, so re-reading returns more. */
  tailable?: boolean;
  /** Content check. Given the file's leading text, is this really the format? */
  claims?: (text: string) => boolean;
  /**
   * Parse one source into records, honouring *request*.
   *
   * Async because a reader may have to load a WASM module first. It receives
   * the source's identity, not just its bytes, so a reader that parses
   * expensively can cache by path and re-slice for a new stride instead of
   * re-parsing — re-reading a 3 MB solver log on every zoom would not be
   * usable.
   */
  read: (source: MetricSourceInput, request: MetricReadRequest) => Promise<MetricRecordSample[]>;
}

/** One file handed to a reader: what it is, and where it came from. */
export interface MetricSourceInput {
  /** Path relative to the attempt — stable, so a reader may cache against it. */
  path: string;
  /** The file's text. */
  text: string;
  /**
   * Changes when the file does. A tailable source passes its size or mtime
   * so a reader's cache is invalidated as the run appends.
   */
  revision?: string | number;
}
