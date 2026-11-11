/**
 * The experiment's Workflow view (Figma L06): one toolbar row over the bound
 * workflow, shown as a Graph or as its Source.
 *
 * - A definition has no status: the canvas is drawn neutral (`definition`).
 * - A document workflow is editable — move and connect on the Graph, or edit
 *   its IR JSON in Source; both save through {@link workflowApi}. A code
 *   workflow is read only and its Source is the `.py`.
 * - Unsaved edits mark the view and its editor tab with ●; ⌘S saves; Discard
 *   and leaving ask through the L13 dialog; a failed save is one band and the
 *   edit is kept.
 * - A click on a task previews its definition (L12).
 *
 * Raw workspace-file `workflow.json` previews (a run's journal, with status)
 * are {@link WorkflowFileViewer}.
 */

import { CircleX, X } from "lucide-react";
import { type JSX, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { workflowApi } from "@/api";
import { experimentPath } from "@/app/entities/paths";
import { usePreview } from "@/app/preview/PreviewContext";
import { useUnsavedEdits } from "@/app/shell/useUnsavedEdits";
import type { ScopedRendererProps } from "@/app/types";
import { WorkbenchIconAction } from "@/components/workbench";
import {
  buildFlowgramDocument,
  type FlowgramDocument,
  flowgramDocToTaskGraphJson,
  normalizeTaskGraph,
  taskGraphToWireDocument,
} from "@/components/workflow/flowgram-document";
import type { TaskGraphJson } from "@/components/workflow/task-graph-ir";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { type CanvasTools, FlowgramCanvas } from "@/plugins/workflow/flowgram-canvas";
import { WorkflowActions, type WorkflowMode } from "./WorkflowActions";
import { CodeSource, DocumentSource } from "./WorkflowSource";
import { WorkflowTaskList } from "./WorkflowTaskList";
import { workflowEditPolicy } from "./workflowEditPolicy";

/** The source text of a document workflow: its IR, pretty-printed when it parses. */
const prettySource = (raw: string | null | undefined, graph: TaskGraphJson | null): string => {
  if (raw) {
    try {
      return JSON.stringify(JSON.parse(raw), null, 2);
    } catch {
      return raw;
    }
  }
  return graph ? JSON.stringify(taskGraphToWireDocument(graph), null, 2) : "";
};

const ErrorBand = ({ message, onDismiss }: { message: string; onDismiss: () => void }) => (
  <div
    role="alert"
    className="flex h-7 min-w-0 flex-none items-center gap-2 border-b border-status-failed/30 bg-status-failed-soft pr-2 pl-6 text-label text-status-failed-foreground"
  >
    <CircleX aria-hidden className="size-icon-sm shrink-0" />
    <span className="min-w-0 flex-1 truncate" title={message}>
      {message}
    </span>
    <WorkbenchIconAction label="Dismiss error" onClick={onDismiss}>
      <X aria-hidden />
    </WorkbenchIconAction>
  </div>
);

export const WorkflowGraphViewer = ({
  selection,
  snapshot,
  onRefresh,
}: ScopedRendererProps<"experiments" | "runs" | "workflows" | "workspaces">): JSX.Element => {
  const preview = usePreview();
  const workflow = snapshot.workflows.find((item) => item.id === selection.objectId) ?? null;
  const experiment = workflow
    ? (snapshot.experiments.find((item) => item.id === workflow.experimentId) ?? null)
    : null;

  const phone = useIsMobile();
  const [chosen, setMode] = useState<WorkflowMode | null>(null);
  // Phones open on the task list; Source is a desktop view.
  const mode: WorkflowMode = chosen ?? (phone ? "list" : "graph");
  const [savedGraph, setSavedGraph] = useState<TaskGraphJson | null>(null);
  const [draft, setDraft] = useState<FlowgramDocument | null>(null);
  const [sourceDraft, setSourceDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [tools, setTools] = useState<CanvasTools | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Bumped on save/discard to re-initialise the canvas (flowgram reads initialData on mount).
  const [revision, setRevision] = useState(0);

  // biome-ignore lint/correctness/useExhaustiveDependencies: objectId is a reset trigger
  useEffect(() => {
    setSavedGraph(null);
    setDraft(null);
    setSourceDraft(null);
    setError(null);
  }, [selection.objectId]);

  const dirty = draft !== null || sourceDraft !== null;

  const graph = savedGraph ?? workflow?.graph ?? null;
  const document = useMemo<FlowgramDocument | null>(
    () => (graph ? buildFlowgramDocument(graph) : null),
    [graph],
  );
  const sourceText = useMemo(
    () =>
      savedGraph
        ? prettySource(null, savedGraph)
        : prettySource(experiment?.workflowSource, workflow?.graph ?? null),
    [savedGraph, experiment?.workflowSource, workflow?.graph],
  );

  const persist = useCallback(
    async (wire: Record<string, unknown>): Promise<void> => {
      if (!workflow) return;
      const persisted = await workflowApi.save(workflow.projectId, workflow.experimentId, wire);
      setSavedGraph(normalizeTaskGraph(persisted));
      setDraft(null);
      setSourceDraft(null);
      setRevision((value) => value + 1);
      onRefresh();
    },
    [workflow, onRefresh],
  );

  const handleSave = useCallback(async (): Promise<void> => {
    if (!workflow || !dirty) return;
    let wire: Record<string, unknown>;
    if (sourceDraft !== null) {
      try {
        wire = JSON.parse(sourceDraft) as Record<string, unknown>;
      } catch (parseError) {
        setError(
          `Couldn't save: the source is not valid JSON (${parseError instanceof Error ? parseError.message : "parse error"})`,
        );
        return;
      }
    } else if (draft) {
      try {
        wire = taskGraphToWireDocument(
          flowgramDocToTaskGraphJson(draft, workflow.name ?? "Workflow"),
        );
      } catch (convertError) {
        setError(
          `Couldn't save: the edited graph could not be read back (${convertError instanceof Error ? convertError.message : "unknown error"})`,
        );
        return;
      }
    } else {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await persist(wire);
    } catch (saveError) {
      // Keep the draft so the user can fix and retry — never silently lose edits.
      setError(
        saveError instanceof Error
          ? `Couldn't save: ${saveError.message}`
          : "Couldn't save the workflow. Check your connection and try again.",
      );
    } finally {
      setSaving(false);
    }
  }, [workflow, dirty, sourceDraft, draft, persist]);

  const leaveDialog = useUnsavedEdits({
    dirty,
    saving,
    onSave: () => void handleSave(),
    subject: `the ${experiment?.name ?? workflow?.name ?? ""} workflow`,
    markPath: experiment ? experimentPath(experiment.projectId, experiment.id) : null,
  });

  if (!workflow) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-label text-muted-foreground">
        No workflow data found.
      </div>
    );
  }

  const policy = workflowEditPolicy(experiment?.workflowKind);
  const readOnly = policy.mode === "convert";
  const code = experiment?.workflowKind === "code";
  const codePath =
    experiment?.workflowFile || (experiment?.workflowEntrypoint ?? "").split(":")[0] || "";
  const isEmpty = !document || document.nodes.length === 0;

  // No toolbar row (retrofit R7 / R8): the view's icons go to the tab row; ⌘S saves.
  const toolbar = (canvasTools: CanvasTools | null): ReactNode => (
    <>
      <WorkflowActions
        readOnly={readOnly}
        phone={phone}
        mode={mode}
        onModeChange={setMode}
        tools={canvasTools}
        dirty={dirty}
        saving={saving}
        onSave={() => void handleSave()}
      />
      {error ? <ErrorBand message={error} onDismiss={() => setError(null)} /> : null}
    </>
  );

  const previewTask = (taskId: string): void => {
    if (!experiment) return;
    preview.preview({
      kind: "node",
      projectId: experiment.projectId,
      experimentId: experiment.id,
      taskId,
    });
  };

  const body =
    mode === "list" && graph ? (
      <div className="flex h-full min-h-0 flex-col">
        {toolbar(null)}
        <div className="min-h-0 flex-1">
          <WorkflowTaskList graph={graph} onPreview={previewTask} />
        </div>
      </div>
    ) : mode === "source" ? (
      <div className="flex h-full min-h-0 flex-col">
        {toolbar(null)}
        <div className="min-h-0 flex-1">
          {code ? (
            <CodeSource path={codePath} />
          ) : (
            <DocumentSource
              key={`${workflow.id}:${revision}`}
              text={sourceDraft ?? sourceText}
              readOnly={readOnly}
              onChange={(next) => setSourceDraft(next === sourceText ? null : next)}
            />
          )}
        </div>
      </div>
    ) : isEmpty ? (
      <div className="flex h-full min-h-0 flex-col">
        {toolbar(null)}
        <div className="flex flex-1 flex-col items-center justify-center gap-1 px-6 text-center">
          <p className="text-body text-foreground">No tasks in this workflow yet</p>
          <p className="max-w-sm text-label text-muted-foreground">
            Its graph is empty or has not been compiled. Source shows the definition.
          </p>
        </div>
      </div>
    ) : (
      <div className="flex h-full min-h-0 flex-col">
        {toolbar(tools)}
        <div className="min-h-0 flex-1">
          <FlowgramCanvas
            key={`${workflow.id}:${revision}:${readOnly ? "ro" : "rw"}`}
            document={document ?? { nodes: [], edges: [] }}
            editable={!readOnly && sourceDraft === null}
            definition
            onTools={setTools}
            onChange={setDraft}
            onNodeClick={previewTask}
          />
        </div>
      </div>
    );

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {body}
      {leaveDialog}
    </div>
  );
};
