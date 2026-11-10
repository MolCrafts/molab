/**
 * The Preview overlay (L12): anchored to the editor's content area, 400 wide
 * (360 at 768–1023), never reflowing the page under it. One component renders
 * every kind; a plugin that registered a right-slot inspector appears as a
 * section under Level 3. Esc closes it once no menu or dialog is open.
 */

import { type JSX, useEffect } from "react";
import { LazySurface } from "@/app/layout/LazySurface";
import { resolveRenderersForSelection } from "@/app/registry";
import type { InspectorTarget, Selection, WorkspaceSnapshot } from "@/app/types";
import { cn } from "@/lib/utils";
import { ContainerPreview } from "./ContainerPreview";
import { ContentPreview } from "./ContentPreview";
import { usePreview } from "./PreviewContext";
import { RunPreview } from "./RunPreview";
import { TaskPreview } from "./TaskPreview";
import { type PreviewTarget, previewKey } from "./target";

/** The selection a plugin's right-slot renderer understands. */
export const selectionOfTarget = (target: PreviewTarget): Selection => {
  switch (target.kind) {
    case "run":
    case "attempt":
      return { objectType: "run", objectId: target.runId };
    case "task":
      return {
        objectType: "task",
        objectId: target.taskId,
        taskId: target.taskId,
        runId: target.runId,
      };
    case "node":
      return { objectType: "task", objectId: target.taskId, taskId: target.taskId, runId: "" };
    case "experiment":
      return { objectType: "experiment", objectId: target.experimentId };
    case "project":
      return { objectType: "project", objectId: target.projectId };
    case "asset":
      return { objectType: "asset", objectId: target.assetId };
    case "file":
      return {
        objectType: "workspace-file",
        objectId: target.filePath,
        filePath: target.filePath,
        fileKind: target.fileKind,
      };
    case "knowledge":
      return { objectType: "knowledge", objectId: target.path };
  }
};

const NO_INSPECTOR: InspectorTarget = { kind: "object", objectType: "run", objectId: "" };

const PluginSections = ({
  target,
  snapshot,
  onRefresh,
}: {
  target: PreviewTarget;
  snapshot: WorkspaceSnapshot;
  onRefresh: () => void;
}): JSX.Element | null => {
  const selection = selectionOfTarget(target);
  const renderers = resolveRenderersForSelection(selection, snapshot, "right");
  if (renderers.length === 0) return null;
  return (
    <div className="flex-none space-y-3 border-t border-border px-4 py-3">
      {renderers.map((renderer) => (
        <section key={renderer.id} aria-label={renderer.title}>
          <h3 className="pb-1 text-label text-muted-foreground">{renderer.title}</h3>
          <LazySurface
            resetKey={`preview:${renderer.id}:${selection.objectId}`}
            loadingTitle={`Loading ${renderer.title}…`}
            errorTitle={`Could not load ${renderer.title}`}
          >
            <renderer.Component
              selection={selection}
              snapshot={snapshot}
              inspectorTarget={NO_INSPECTOR}
              onInspectorTargetChange={() => {}}
              onRefresh={onRefresh}
            />
          </LazySurface>
        </section>
      ))}
    </div>
  );
};

const overlayOpen = (): boolean =>
  document.querySelector('[role="dialog"], [role="menu"], [role="listbox"]') !== null;

export const PreviewBody = ({
  target,
  snapshot,
  onRefresh,
}: {
  target: PreviewTarget;
  snapshot: WorkspaceSnapshot;
  onRefresh: () => void;
}): JSX.Element => {
  const controls = usePreview();
  const common = {
    snapshot,
    onPreview: controls.preview,
    onOpen: (next: PreviewTarget, path?: string) => controls.open(next, { path }),
    onOpenInBackground: () => controls.open(target, { background: true }),
    onClose: controls.close,
  };
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1">
        {target.kind === "run" || target.kind === "attempt" ? (
          <RunPreview key={previewKey(target)} target={target} onRefresh={onRefresh} {...common} />
        ) : target.kind === "task" || target.kind === "node" ? (
          <TaskPreview key={previewKey(target)} target={target} {...common} />
        ) : target.kind === "experiment" || target.kind === "project" ? (
          <ContainerPreview key={previewKey(target)} target={target} {...common} />
        ) : (
          <ContentPreview key={previewKey(target)} target={target} {...common} />
        )}
      </div>
      <PluginSections target={target} snapshot={snapshot} onRefresh={onRefresh} />
    </div>
  );
};

interface PreviewOverlayProps {
  snapshot: WorkspaceSnapshot;
  narrow: boolean;
  /** False unless the active tab is an italic preview and the target is an item inside it. */
  open: boolean;
  onRefresh: () => void;
}

/** Desktop overlay; phones render `PreviewBody` in a bottom sheet instead. */
export const PreviewOverlay = ({
  snapshot,
  narrow,
  open,
  onRefresh,
}: PreviewOverlayProps): JSX.Element | null => {
  const { target, close } = usePreview();

  useEffect(() => {
    if (!open || !target) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== "Escape" || event.defaultPrevented || overlayOpen()) return;
      close();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, target, close]);

  if (!open || !target) return null;
  return (
    <aside
      aria-label="Preview"
      data-shell-region="preview"
      className={cn(
        "mol-motion-enter-from-right absolute top-2 right-2 bottom-2 z-20 overflow-hidden rounded-overlay border border-border bg-background shadow-overlay",
        narrow ? "w-shell-preview-narrow" : "w-shell-preview",
      )}
    >
      <PreviewBody target={target} snapshot={snapshot} onRefresh={onRefresh} />
    </aside>
  );
};
