import { Save } from "lucide-react";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { workspaceApi } from "@/app/state/api";
import type { RendererProps } from "@/app/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  WorkbenchAction,
  WorkbenchIconAction,
  WorkbenchOperationState,
} from "@/components/workbench";
import { filePreviewPluginRegistry } from "@/lib/file-preview-plugins";
import { fileSizeGate, treeFileSize, windowForDecision } from "@/lib/fileSizeGate";

/**
 * Monaco-backed text editor for workspace files.
 *
 * Lazy-loaded so `@monaco-editor/react` / `monaco-editor` (a large
 * dependency) is split into an async chunk fetched only when the editor
 * actually mounts, instead of riding in the initial page-load bundle.
 *
 * Preview-host contract: this component is the host of the `editor` panel
 * slot (see `./index.ts`). It renders an Edit/Preview tab pair and, in the
 * Preview tab, delegates to whichever {@link FilePreviewPlugin} the
 * `filePreviewPluginRegistry` resolves for the current file. The preview
 * *content* is supplied by other plugins (core markdown/workflow, molvis,
 * …); this editor only owns the hosting surface.
 */
const Editor = lazy(() => import("@monaco-editor/react"));

export const TextEditor = ({ selection, snapshot }: RendererProps): JSX.Element => {
  const [value, setValue] = useState<string>("");
  const [status, setStatus] = useState<"idle" | "loading" | "saving" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  // A file above the size cap is not fetched until the user asks for it, so
  // opening a multi-gigabyte artifact by accident costs nothing.
  const [confirmedPath, setConfirmedPath] = useState<string | null>(null);
  // Set when the server returned only part of the file, so the editor can say
  // so rather than letting the user believe they are editing the whole thing.
  const [shownBytes, setShownBytes] = useState<{ shown: number; total: number } | null>(null);
  const sizeDecision = useMemo(() => {
    if (selection.objectType !== "workspace-file") return fileSizeGate(null);
    return fileSizeGate(treeFileSize(snapshot.workspaceRoot, selection.objectId));
  }, [selection, snapshot.workspaceRoot]);
  const blockedBySize = sizeDecision.kind === "oversized" && confirmedPath !== selection.objectId;
  const previewPlugin = useMemo(() => {
    if (selection.objectType !== "workspace-file") {
      return null;
    }

    const name = selection.filePath.split("/").pop() ?? selection.filePath;
    return filePreviewPluginRegistry.getPluginForFile(name, selection.filePath, {
      hasPreviewSidecar: selection.hasPreviewSidecar,
    });
  }, [selection]);

  const language = useMemo(() => {
    if (selection.objectType !== "workspace-file") {
      return "plaintext";
    }
    const kind = selection.fileKind;
    if (kind === "json") return "json";
    if (kind === "yaml") return "yaml";
    if (kind === "python") return "python";
    if (kind === "markdown") return "markdown";
    if (kind === "text") return "plaintext";
    return "plaintext";
  }, [selection]);

  useEffect(() => {
    if (selection.objectType !== "workspace-file" || blockedBySize) {
      return;
    }

    let isMounted = true;
    setStatus("loading");
    setError(null);
    workspaceApi
      // An oversized file the user confirmed is fetched as a bounded head
      // window, never in full — the gate decided how much is safe to pull.
      .getWorkspaceFileWindow(selection.objectId, windowForDecision(sizeDecision, "head"))
      .then((response) => {
        if (isMounted) {
          setValue(response.content);
          setShownBytes(
            response.truncated
              ? { shown: response.content.length, total: response.totalBytes ?? 0 }
              : null,
          );
          setStatus("idle");
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Failed to load file");
          setStatus("error");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [selection, blockedBySize, sizeDecision]);

  const handleSave = async () => {
    if (selection.objectType !== "workspace-file") return;

    setStatus("saving");
    try {
      await workspaceApi.writeFile(selection.objectId, value);
      setStatus("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save file");
      setStatus("error");
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <header className="flex h-10 flex-none items-center justify-between gap-2 border-b border-border px-3">
        <p className="min-w-0 truncate font-mono text-label text-muted-foreground tabular-nums">
          {selection.objectId}
        </p>
        <WorkbenchIconAction
          label={status === "saving" ? "Saving file" : "Save file"}
          onClick={handleSave}
          disabled={status === "loading" || status === "saving" || shownBytes !== null}
        >
          <Save className="h-3.5 w-3.5" />
        </WorkbenchIconAction>
      </header>
      {shownBytes ? (
        <p className="flex-none border-b border-border bg-muted px-3 py-1 text-label text-muted-foreground tabular-nums">
          Showing the first {shownBytes.shown.toLocaleString()} of{" "}
          {shownBytes.total.toLocaleString()} bytes — read-only while truncated.
        </p>
      ) : null}
      <div className="min-h-0 flex-1">
        {blockedBySize && sizeDecision.kind === "oversized" ? (
          <WorkbenchOperationState
            kind="empty"
            title="File is too large to open automatically"
            detail={`${sizeDecision.sizeLabel} — loading it in full would stall the editor.`}
            action={
              <WorkbenchAction
                kind="ghost"
                size="compact"
                onClick={() => setConfirmedPath(selection.objectId)}
              >
                Load anyway
              </WorkbenchAction>
            }
          />
        ) : status === "loading" && !value ? (
          <WorkbenchOperationState kind="loading" title="Loading file…" skeletonRows={6} />
        ) : status === "error" ? (
          <WorkbenchOperationState
            kind="error"
            title="Could not load file"
            detail={error ?? undefined}
          />
        ) : (
          <Tabs defaultValue="edit" className="flex h-full flex-col gap-0">
            {previewPlugin ? (
              <div className="flex-none border-b border-border px-3 py-2">
                <TabsList className="h-control-compact w-fit rounded-control bg-muted p-1">
                  <TabsTrigger value="edit" className="h-6 text-label">
                    Edit
                  </TabsTrigger>
                  <TabsTrigger value="preview" className="h-6 text-label">
                    Preview
                  </TabsTrigger>
                </TabsList>
              </div>
            ) : null}

            <TabsContent value="edit" className="m-0 min-h-0 flex-1">
              <Suspense
                fallback={
                  <div className="p-3 text-label text-muted-foreground">Loading editor…</div>
                }
              >
                <Editor
                  height="100%"
                  language={language}
                  value={value}
                  theme="light"
                  onChange={(nextValue) => {
                    setValue(nextValue ?? "");
                  }}
                  options={{
                    minimap: { enabled: false },
                    // Read-only for an oversized file, and for a truncated
                    // window — saving a prefix back would destroy the tail.
                    readOnly: sizeDecision.kind === "oversized" || shownBytes !== null,
                    wordWrap: "on",
                    scrollBeyondLastLine: false,
                  }}
                />
              </Suspense>
            </TabsContent>

            {previewPlugin && selection.objectType === "workspace-file" ? (
              <TabsContent value="preview" className="m-0 min-h-0 flex-1 overflow-auto">
                <previewPlugin.Component
                  content={value}
                  name={selection.filePath.split("/").pop() ?? selection.filePath}
                  path={selection.filePath}
                  folderId="workspace"
                  assetId={
                    selection.objectType === "workspace-file" ? selection.assetId : undefined
                  }
                />
              </TabsContent>
            ) : null}
          </Tabs>
        )}
      </div>
    </div>
  );
};
