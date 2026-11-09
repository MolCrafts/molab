/**
 * The editor of a workspace file (Figma L07-1 … L07-5): the text in Monaco,
 * with no header row — the editor tab names the file, the breadcrumb gives its
 * path. Its actions sit in the tab row as icons only (owner rule: icon OR text):
 * Save (lit while there are edits), Preview and Preview to the side (when a
 * preview plugin claims the file), ⋯ with Download and Copy path.
 *
 * Edits mark the tab ●, ⌘S saves, leaving asks (L13). A failed save is one red
 * text band and the edits stay — it used to replace the editor with “Could not
 * load file” and lose them. File text is a TanStack query.
 *
 * Preview-host contract: the preview *content* comes from whichever
 * `FilePreviewPlugin` the registry resolves (markdown, TeX, structures, …);
 * this editor only hosts it.
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@molcrafts/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleX, Columns2, Eye, MoreHorizontal, Save, X } from "lucide-react";
import { type JSX, Suspense, useCallback, useMemo, useState } from "react";
import { workspaceApi } from "@/api";
import { LazySurface } from "@/app/layout/LazySurface";
import { fileEditorMark } from "@/app/shell/dirtyEditors";
import { EditorActions } from "@/app/shell/editorActions";
import { useUnsavedEdits } from "@/app/shell/useUnsavedEdits";
import { fileKeys, workspaceFileTextQueryOptions } from "@/app/state/entityQueries";
import type { FileKind, RendererProps } from "@/app/types";
import { toast } from "@/components/ui/toast";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
  WorkbenchToggleAction,
} from "@/components/workbench";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import type { FilePreviewPlugin } from "@/lib/file-preview-plugins";
import { filePreviewPluginRegistry } from "@/lib/file-preview-plugins";
import { useUiTheme } from "@/lib/ui-theme";
import { MonacoEditor } from "./MonacoEditor";

type Layout = "source" | "preview" | "split";

const LANGUAGE: Partial<Record<FileKind, string>> = {
  json: "json",
  yaml: "yaml",
  python: "python",
  markdown: "markdown",
};

/** The last layout chosen for a kind of preview (a per-viewer convenience). */
const layoutKey = (pluginId: string): string => `molab.editor.layout.${pluginId}`;
const readLayout = (pluginId: string): Layout => {
  try {
    const stored = window.localStorage.getItem(layoutKey(pluginId));
    return stored === "preview" || stored === "split" ? stored : "source";
  } catch {
    return "source";
  }
};
const writeLayout = (pluginId: string, layout: Layout): void => {
  try {
    window.localStorage.setItem(layoutKey(pluginId), layout);
  } catch {
    // Storage blocked: the choice simply is not remembered.
  }
};

const nameOf = (path: string): string => path.split("/").pop() ?? path;

const PreviewPane = ({
  plugin,
  text,
  path,
  assetId,
}: {
  plugin: FilePreviewPlugin;
  text: string;
  path: string;
  assetId?: string;
}): JSX.Element => (
  <div className="h-full min-h-0 overflow-auto bg-background">
    <LazySurface
      resetKey={`file-preview:${plugin.id}:${path}`}
      loadingTitle={`Loading ${plugin.name} preview…`}
    >
      <plugin.Component
        content={text}
        name={nameOf(path)}
        path={path}
        folderId="workspace"
        assetId={assetId}
      />
    </LazySurface>
  </div>
);

const FileEditor = ({
  path,
  fileKind,
  plugin,
  assetId,
}: {
  path: string;
  fileKind: FileKind;
  plugin: FilePreviewPlugin | null;
  assetId?: string;
}): JSX.Element => {
  const theme = useUiTheme();
  const queryClient = useQueryClient();
  const query = useQuery(workspaceFileTextQueryOptions(path));
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [layout, setLayoutState] = useState<Layout>(() =>
    plugin ? readLayout(plugin.id) : "source",
  );
  const setLayout = (next: Layout): void => {
    setLayoutState(next);
    if (plugin) writeLayout(plugin.id, next);
  };

  const saved = query.data ?? "";
  const text = draft ?? saved;
  const dirty = draft !== null;

  const save = useCallback(async (): Promise<void> => {
    if (draft === null) return;
    setSaving(true);
    setError(null);
    try {
      await workspaceApi.writeFile(path, draft);
      queryClient.setQueryData(fileKeys.text(path), draft);
      setDraft(null);
    } catch (saveError) {
      // The editor and the edits stay; the band says why (L07-4).
      setError(
        `Couldn't save ${nameOf(path)} — ${saveError instanceof Error ? saveError.message : "the server refused it"}. Your edits are kept.`,
      );
    } finally {
      setSaving(false);
    }
  }, [draft, path, queryClient]);

  const leaveDialog = useUnsavedEdits({
    dirty,
    saving,
    onSave: () => void save(),
    subject: nameOf(path),
    markPath: fileEditorMark(path),
    sameEditor: (current, next) =>
      current.pathname === next.pathname &&
      new URLSearchParams(current.search).get("file") ===
        new URLSearchParams(next.search).get("file"),
  });

  const actions = (
    <div className="flex items-center gap-hairline">
      {dirty ? (
        // Only while there is something to save (L07-1 / L07-3); the tab carries ● too.
        <WorkbenchIconAction
          label={saving ? "Saving…" : "Save"}
          shortcut="⌘S"
          disabled={saving}
          className="text-accent"
          onClick={() => void save()}
        >
          <Save aria-hidden />
        </WorkbenchIconAction>
      ) : null}
      {plugin ? (
        <>
          <WorkbenchToggleAction
            label="Preview"
            pressed={layout === "preview"}
            onClick={() => setLayout(layout === "preview" ? "source" : "preview")}
          >
            <Eye aria-hidden className="size-icon" />
          </WorkbenchToggleAction>
          <WorkbenchToggleAction
            label="Preview to the side"
            pressed={layout === "split"}
            onClick={() => setLayout(layout === "split" ? "source" : "split")}
            className="max-md:hidden"
          >
            <Columns2 aria-hidden className="size-icon" />
          </WorkbenchToggleAction>
        </>
      ) : null}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <WorkbenchIconAction label="More actions">
            <MoreHorizontal aria-hidden />
          </WorkbenchIconAction>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuItem asChild>
            <a href={workspaceApi.downloadUrl(path)} download={nameOf(path)}>
              Download
            </a>
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={() => {
              void navigator.clipboard.writeText(path);
              toast("Copied path");
            }}
          >
            Copy path
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );

  if (query.isPending) {
    return <WorkbenchOperationState kind="loading" title="Loading file…" skeletonRows={6} />;
  }
  if (query.isError) {
    return (
      <WorkbenchOperationState
        kind="error"
        title="Could not load file"
        detail={query.error instanceof Error ? query.error.message : path}
        action={<WorkbenchRetryAction onClick={() => void query.refetch()} />}
      />
    );
  }

  const source = (
    <Suspense fallback={<WorkbenchOperationState kind="loading" title="Loading editor…" />}>
      <MonacoEditor
        height="100%"
        language={LANGUAGE[fileKind] ?? "plaintext"}
        value={text}
        theme={theme === "dark" ? "vs-dark" : "light"}
        onChange={(next) => setDraft((next ?? "") === saved ? null : (next ?? ""))}
        options={{ minimap: { enabled: false }, wordWrap: "on", scrollBeyondLastLine: false }}
      />
    </Suspense>
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <EditorActions>{actions}</EditorActions>
      {error ? (
        <div
          role="alert"
          className="flex h-7 flex-none items-center gap-2 border-b border-status-failed/30 bg-status-failed-soft pr-2 pl-6 text-label text-status-failed-foreground"
        >
          {/* Error bands keep their glyph (retrofit R9 declined). */}
          <CircleX aria-hidden className="size-icon-sm shrink-0" />
          <span className="min-w-0 flex-1 truncate" title={error}>
            {error}
          </span>
          <WorkbenchIconAction label="Dismiss" onClick={() => setError(null)}>
            <X aria-hidden />
          </WorkbenchIconAction>
        </div>
      ) : null}
      <div className="flex min-h-0 flex-1">
        {plugin && layout === "preview" ? (
          <div className="min-w-0 flex-1">
            <PreviewPane plugin={plugin} text={text} path={path} assetId={assetId} />
          </div>
        ) : (
          <>
            <div className="min-w-0 flex-1">{source}</div>
            {plugin && layout === "split" ? (
              <div className="min-w-0 flex-1 border-l border-border max-md:hidden">
                <PreviewPane plugin={plugin} text={text} path={path} assetId={assetId} />
              </div>
            ) : null}
          </>
        )}
      </div>
      {leaveDialog}
    </div>
  );
};

export const TextEditor = ({ selection }: RendererProps): JSX.Element => {
  const contributionGeneration = useContributionGeneration();
  const plugin = useMemo(() => {
    void contributionGeneration;
    if (selection.objectType !== "workspace-file") return null;
    return filePreviewPluginRegistry.getPluginForFile(
      nameOf(selection.filePath),
      selection.filePath,
      {
        hasPreviewSidecar: selection.hasPreviewSidecar,
      },
    );
  }, [selection, contributionGeneration]);

  if (selection.objectType !== "workspace-file") {
    return <WorkbenchOperationState kind="empty" title="Not a file" />;
  }
  return (
    <FileEditor
      key={selection.objectId}
      path={selection.objectId}
      fileKind={selection.fileKind}
      plugin={plugin}
      assetId={selection.assetId}
    />
  );
};
