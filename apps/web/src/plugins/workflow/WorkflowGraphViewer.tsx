/**
 * WorkflowGraphViewer — the workflow "Graph" tab. Renders the workflow entity's
 * task-graph IR (from the snapshot, or the just-saved draft) on the editable
 * flowgram free-layout canvas, and saves edits back via {@link workflowApi}.
 * Clicking a node opens the right-panel TaskViewer via `inspectedTask`.
 *
 * Editing safety: a failed save surfaces a dismissible error and keeps the draft
 * so the user can retry; ⌘S/Ctrl+S saves; navigating away (in-app or full
 * unload) with unsaved edits prompts to confirm; Discard reverts to the last
 * saved graph.
 *
 * Raw workspace-file `workflow.json` previews are a different source + format
 * and are handled by {@link WorkflowFileViewer}; this viewer only ever receives
 * ``workflow`` entity selections (it is mounted solely by WorkflowViewer).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useBlocker } from "react-router-dom";
import { workflowApi } from "@/api";
import { useInspectedTask } from "@/app/state/inspectedTask";
import type { ScopedRendererProps } from "@/app/types";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { WorkbenchAction, WorkbenchDismissAction } from "@/components/workbench";
import { FlowgramCanvas } from "@/components/workflow/flowgram-canvas";
import { FlowgramCanvasToolbar } from "@/components/workflow/flowgram-canvas-toolbar";
import {
  buildFlowgramDocument,
  type FlowgramDocument,
  flowgramDocToTaskGraphJson,
  normalizeTaskGraph,
  taskGraphToWireDocument,
} from "@/components/workflow/flowgram-document";
import type { TaskGraphJson } from "@/components/workflow/task-graph-ir";
import { workflowEditPolicy } from "./workflowEditPolicy";

export const WorkflowGraphViewer = ({
  selection,
  snapshot,
  onRefresh,
}: ScopedRendererProps<"experiments" | "runs" | "workflows" | "workspaces">): JSX.Element => {
  const { inspectTask } = useInspectedTask();
  const workflow = snapshot.workflows.find((item) => item.id === selection.objectId) ?? null;

  const [savedGraph, setSavedGraph] = useState<TaskGraphJson | null>(null);
  const [draft, setDraft] = useState<FlowgramDocument | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Bumped on save/discard to force the canvas to re-initialize from the
  // authoritative document (flowgram only reads `initialData` on mount).
  const [revision, setRevision] = useState(0);
  const [convertConfirmed, setConvertConfirmed] = useState(false);
  const [convertOpen, setConvertOpen] = useState(false);

  const dirty = draft !== null;

  // Reset edit state whenever the selected workflow changes. objectId is a
  // trigger, not a read — biome's exhaustive-deps can't see that and would
  // strip it, which would leave stale edits when switching workflows.
  // biome-ignore lint/correctness/useExhaustiveDependencies: objectId is a reset trigger
  useEffect(() => {
    setSavedGraph(null);
    setDraft(null);
    setError(null);
    setConvertConfirmed(false);
    setConvertOpen(false);
  }, [selection.objectId]);

  // Prefer the freshly-saved graph, else the snapshot's IR.
  const graph = savedGraph ?? workflow?.graph ?? null;
  const document = useMemo<FlowgramDocument | null>(
    () => (graph ? buildFlowgramDocument(graph) : null),
    [graph],
  );

  const handleSave = useCallback(async (): Promise<void> => {
    const source = draft ?? (convertConfirmed ? (document ?? { nodes: [], edges: [] }) : null);
    if (!workflow || !source) return;
    setSaving(true);
    setError(null);
    try {
      const wire = taskGraphToWireDocument(
        flowgramDocToTaskGraphJson(source, workflow.name ?? "Workflow"),
      );
      const persisted = await workflowApi.save(workflow.projectId, workflow.experimentId, wire, {
        convertToDocument: convertConfirmed,
      });
      // Reload from the server-normalized document so the canvas reflects
      // exactly what was persisted, and remount it to drop the stale draft.
      setSavedGraph(normalizeTaskGraph(persisted));
      setDraft(null);
      setRevision((r) => r + 1);
      if (convertConfirmed) onRefresh();
    } catch (err) {
      // Keep `draft` so the user can fix and retry — never silently lose edits.
      setError(
        err instanceof Error
          ? `Couldn't save workflow: ${err.message}`
          : "Couldn't save workflow. Check your connection and try again.",
      );
    } finally {
      setSaving(false);
    }
  }, [workflow, draft, document, convertConfirmed, onRefresh]);

  const handleDiscard = useCallback((): void => {
    setDraft(null);
    setError(null);
    setRevision((r) => r + 1);
  }, []);

  // ⌘S / Ctrl+S saves when there are unsaved edits.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        if (!dirty || saving) return;
        event.preventDefault();
        void handleSave();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dirty, saving, handleSave]);

  // Warn before a full-page unload (refresh / close / external nav) while dirty.
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent): void => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  // Intercept in-app navigation (e.g. selecting another workflow) while dirty so
  // edits aren't silently dropped. Requires the data router (see index.tsx).
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty && currentLocation.pathname !== nextLocation.pathname,
  );

  // If the edits get saved/discarded while a block is pending, let nav through.
  useEffect(() => {
    if (blocker.state === "blocked" && !dirty) {
      blocker.reset?.();
    }
  }, [blocker, dirty]);

  if (!workflow) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-label text-muted-foreground">
        No workflow data found.
      </div>
    );
  }

  const experiment = snapshot.experiments.find((item) => item.id === workflow.experimentId) ?? null;
  const policy = workflowEditPolicy(experiment?.workflowKind);
  const readOnly = policy.mode === "convert" && !convertConfirmed;
  const entrypoint = experiment?.workflowEntrypoint;
  const isEmpty = !document || document.nodes.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="relative min-h-0 w-full flex-1">
        <div className="pointer-events-none absolute inset-x-0 top-0 z-50 flex flex-col gap-2 px-3 py-3">
          <div className="flex items-start justify-end gap-2">
            <div className="pointer-events-auto flex items-center rounded-control border border-border bg-background/90 px-1 py-1">
              <FlowgramCanvasToolbar
                onSave={handleSave}
                onDiscard={handleDiscard}
                saving={saving}
                dirty={dirty || (policy.mode === "convert" && convertConfirmed)}
              />
            </div>
          </div>

          {readOnly && policy.mode === "convert" && (
            <div className="pointer-events-auto flex flex-wrap items-center justify-between gap-3 rounded-control border border-border bg-background/90 px-3 py-2 text-label text-foreground">
              <p>
                This experiment runs a {policy.kind} workflow
                {entrypoint ? ` (${entrypoint})` : ""}. The graph is a read-only view.
              </p>
              <WorkbenchAction kind="secondary" size="compact" onClick={() => setConvertOpen(true)}>
                Convert to document…
              </WorkbenchAction>
            </div>
          )}

          {error && (
            <div
              role="alert"
              className="pointer-events-auto flex items-start justify-between gap-3 rounded-control border border-status-failed/30 bg-status-failed-soft px-3 py-2 text-body text-status-failed-foreground"
            >
              <span>{error}</span>
              <WorkbenchDismissAction
                label="Dismiss error"
                onClick={() => setError(null)}
                className="-mr-1 size-6 shrink-0 text-status-failed-foreground/80 hover:text-status-failed-foreground"
              />
            </div>
          )}
        </div>

        {isEmpty && policy.mode !== "convert" ? (
          <div className="flex h-full flex-col items-center justify-center gap-1 px-6 text-center">
            <p className="text-body font-medium text-foreground">No tasks in this workflow yet</p>
            <p className="max-w-sm text-label text-muted-foreground">
              Its graph is empty or hasn&apos;t been compiled. Open the Source tab to view or edit
              the workflow definition.
            </p>
          </div>
        ) : readOnly ? (
          <FlowgramCanvas
            key={`${workflow.id}:${revision}:ro`}
            document={document ?? { nodes: [], edges: [] }}
            editable={false}
            onChange={setDraft}
            onNodeClick={(taskId) => inspectTask(taskId, "")}
          />
        ) : (
          <FlowgramCanvas
            key={`${workflow.id}:${revision}`}
            document={document ?? { nodes: [], edges: [] }}
            editable
            onChange={setDraft}
            onNodeClick={(taskId) => inspectTask(taskId, "")}
          />
        )}
      </div>

      <AlertDialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open) blocker.reset?.();
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Leave with unsaved changes?</AlertDialogTitle>
            <AlertDialogDescription>
              Your edits to this workflow graph haven&apos;t been saved. Leaving now discards them.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => blocker.reset?.()}>Stay</AlertDialogCancel>
            <AlertDialogAction intent="danger" onClick={() => blocker.proceed?.()}>
              Leave
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={convertOpen} onOpenChange={setConvertOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Convert to document?</AlertDialogTitle>
            <AlertDialogDescription>
              Saving an edited graph rebinds this experiment to the graph document and creates a new
              revision; future runs execute the graph, not the code entrypoint.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setConvertConfirmed(true);
                setConvertOpen(false);
              }}
            >
              Convert to document
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
