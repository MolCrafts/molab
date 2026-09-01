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
