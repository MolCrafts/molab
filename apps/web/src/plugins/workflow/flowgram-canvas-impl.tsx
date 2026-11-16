/**
 * FlowgramCanvas — the single read-only workflow canvas, built on the
 * `@flowgram.ai/free-layout-editor` free-layout core.
 *
 * Every workflow surface (the run "what ran" preview, the workflow Graph tab,
 * the workspace `workflow.json` viewer) renders through this one component.
 * Nodes are drawn with molab's own shadcn/ui + Tailwind chrome (NO FlowGram
 * form-materials / Semi Design / Ant Design). The canvas is read-only by
 * default; pass `editable` to enable drag / connect / add / remove with
 * undo-redo history, and `onChange` to receive the edited document for
 * write-back (see WorkflowGraphViewer).
 */

import {
  EditorRenderer,
  FreeLayoutEditorProvider,
  type FreeLayoutProps,
  useAutoLayout,
  useClientContext,
  useNodeRender,
  usePlaygroundTools,
  type WorkflowNodeProps,
  WorkflowNodeRenderer,
} from "@flowgram.ai/free-layout-editor";
import "@flowgram.ai/free-layout-editor/index.css";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@molcrafts/ui";
import { Layers, Maximize2, Minus, Plus, Redo2, Undo2 } from "lucide-react";
import {
  createContext,
  type JSX,
  type MutableRefObject,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { normalizeStatus, type StatusTone, statusSpec } from "@/app/status/vocabulary";
import { WorkbenchIconAction, WorkflowNode } from "@/components/workbench";
import {
  buildFlowgramDocument,
  type FlowgramDocument,
  type FlowgramNodeData,
} from "@/components/workflow/flowgram-document";
import type { TaskGraphJson } from "@/components/workflow/task-graph-ir";
import { useReducedMotion } from "@/hooks/use-reduced-motion";

/**
 * Node display data keyed by task id. flowgram drops arbitrary node `data` for
 * registry-less generic nodes, so we carry it ourselves and `NodeCard` looks it
 * up by the (reliable) node id via this context.
 */
const NodeDataContext = createContext<Map<string, Partial<FlowgramNodeData>>>(new Map());

/**
 * Lets a `SubWorkflow` node ask the canvas to open its inner graph in a
 * read-only drill-down dialog. Undefined outside a `FlowgramCanvas`.
 */
const SubworkflowExpandContext = createContext<
  ((taskId: string, inner: TaskGraphJson) => void) | undefined
>(undefined);

export interface FlowgramCanvasProps {
  document: FlowgramDocument;
  /** Called with a task id when its node is clicked. */
  onNodeClick?: (taskId: string) => void;
  /** When true the canvas is editable (drag / connect / add / remove). */
  editable?: boolean;
  /**
   * Fires on user edits with the current document (editable mode only).
   * Receives `null` when the undo stack is empty again (discard / undo-all)
   * so the host can clear its dirty flag — mount-time auto-layout never
   * counts as an edit.
   */
  onChange?: (document: FlowgramDocument | null) => void;
  /**
   * A workflow definition (L06): no status anywhere — neutral nodes, grey links,
   * outline ports. A run's canvas leaves this off and keeps its colours.
   */
  definition?: boolean;
  /**
   * Hands the canvas tools to a host toolbar (L06) instead of drawing the
   * floating overlay; called again whenever the zoom changes. The provider does
   * not re-render its children with the host, so the host draws the toolbar.
   */
  onTools?: (tools: CanvasTools) => void;
  className?: string;
}

/** What a toolbar can do to the canvas. */
export interface CanvasTools {
  editable: boolean;
  zoomPercent: number;
  undo: () => void;
  redo: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fit: () => void;
}

const DefinitionContext = createContext(false);

/**
 * Canvas node body — shared {@link WorkflowNode} chrome inside flowgram's
 * `WorkflowNodeRenderer` (ports / drag stay with flowgram).
 */
const NodeCard = ({ onNodeClick }: { onNodeClick?: (taskId: string) => void }): JSX.Element => {
  const render = useNodeRender();
  const definition = useContext(DefinitionContext);
  const nodeDataById = useContext(NodeDataContext);
  const expandSubworkflow = useContext(SubworkflowExpandContext);
  const data = nodeDataById.get(render.id) ?? {};
  const taskId = data.taskId ?? render.id;
  const role = (data.role ?? "task") as "input" | "output" | "task";
  // A definition has no status; a run's canvas shows each task's.
  const status = definition ? null : (data.status ?? "pending");
  const parallel = data.parallel ?? false;
  const subworkflow = data.subworkflow;
  const failed = status !== null && normalizeStatus(status) === "failed";
  const error = failed ? data.error : undefined;
  const displayStatus = status === null ? null : statusSpec(status).word;
  const titleTip = `${taskId} · ${role}${parallel ? " · parallel ×N" : ""}${subworkflow ? " · subworkflow" : ""}${displayStatus ? ` · ${displayStatus}` : ""}${error ? `\n${error}` : ""}`;

  return (
    <div className="relative" title={titleTip}>
      <WorkflowNode
        title={data.title ?? taskId}
        taskType={data.taskType ?? data.subtitle ?? null}
        status={status}
        canvasRole={role}
        subworkflow={Boolean(subworkflow)}
        error={error}
        density="compact"
        onActivate={onNodeClick ? () => onNodeClick(taskId) : undefined}
      />
      {subworkflow && expandSubworkflow && (
        <WorkbenchIconAction
          label={`Open inner workflow of ${taskId}`}
          className="absolute -right-2 -bottom-2 size-4-lg rounded-full border border-border bg-card"
          onClick={(event) => {
            event.stopPropagation();
            expandSubworkflow(taskId, subworkflow);
          }}
        >
          <Layers className="h-3 w-3" />
        </WorkbenchIconAction>
      )}
    </div>
  );
};

/**
 * Triggers flowgram's dagre layered auto-layout once the canvas has mounted and
 * measured its node rects, replacing the IR's coarse fallback grid
 * (flowgram-document.ts). Must live INSIDE FreeLayoutEditorProvider so
 * `useAutoLayout` can resolve the layout service the free-layout preset
 * registers. Runs a frame after mount, then once more shortly after in case the
 * first pass beat the node-size ResizeObserver.
 *
 * Two independent gates:
 * - **visual** (`onVisualReady`) — lift the layout mask once nodes are placed
 * - **dirty** (`settledRef`) — open `onContentChange` only after layout is done,
 *   history is cleared, and a quiet window has passed. Auto-layout emits
 *   MOVE_NODE for every node; those must never set the host dirty flag
 *   (experiment dashboard was prompting "save changes" on leave with zero edits).
 */
const AutoLayoutOnMount = ({
  settledRef,
  ignoreDirtyUntilRef,
  onVisualReady,
}: {
  settledRef: MutableRefObject<boolean>;
  ignoreDirtyUntilRef: MutableRefObject<number>;
  onVisualReady: () => void;
}): null => {
  const autoLayout = useAutoLayout();
  const ctx = useClientContext();
  // `useAutoLayout()` / history clear need stable refs — fresh bound fns every
  // render would re-fire layout on every drag re-render.
  const autoLayoutRef = useRef(autoLayout);
  autoLayoutRef.current = autoLayout;
  const historyRef = useRef(ctx.history);
  historyRef.current = ctx.history;
  const onVisualReadyRef = useRef(onVisualReady);
  onVisualReadyRef.current = onVisualReady;
  const ranRef = useRef(false);
  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;
    let active = true;
    let visualReady = false;
    let dirtyGateOpen = false;

    const run = async () => {
      try {
        await autoLayoutRef.current();
      } catch (err) {
        console.error("[flowgram auto-layout]", err);
      }
    };

    const markVisualReady = (): void => {
      if (!active || visualReady) return;
      visualReady = true;
      onVisualReadyRef.current();
    };

    const openDirtyGate = (): void => {
      if (!active || dirtyGateOpen) return;
      dirtyGateOpen = true;
      // Drop layout-generated undo entries so canUndo() is false until a real
      // user drag/connect. onContentChange keys dirty off canUndo().
      try {
        historyRef.current.clear();
      } catch {
        // Defensive: history should always be bound (see editorProps.history).
      }
      settledRef.current = true;
      // Brief suppress for straggler MOVE_NODEs that land after history.clear().
      ignoreDirtyUntilRef.current = Date.now() + 200;
    };

    const settleAfterLayout = async (): Promise<void> => {
      await run();
      // Residual ResizeObserver / fitView MOVE_NODEs often land a frame or two
      // after the layout promise resolves — wait them out before opening dirty.
      await new Promise<void>((resolve) => {
        window.setTimeout(resolve, 120);
      });
      if (!active) return;
      openDirtyGate();
      markVisualReady();
    };

    const raf = requestAnimationFrame(() => {
      if (active) void run();
    });
    const retry = setTimeout(() => {
      if (active) void settleAfterLayout();
    }, 250);
    // Visual only: never open the dirty gate early (that was the false-dirty bug).
    const failSafe = setTimeout(markVisualReady, 800);
    return () => {
      active = false;
      cancelAnimationFrame(raf);
      clearTimeout(retry);
      clearTimeout(failSafe);
    };
  }, [settledRef, ignoreDirtyUntilRef]);
  return null;
};

/**
 * Canvas controls overlay — zoom out / level / zoom in / fit, plus undo-redo in
 * editable mode. Rendered INSIDE the provider so it can reach the playground
 * tools and history service. Motion respects `prefers-reduced-motion`.
 */
const FlowgramCanvasControls = ({ editable }: { editable: boolean }): JSX.Element => {
  const tools = usePlaygroundTools();
  const ctx = useClientContext();
  const reducedMotion = useReducedMotion();
  const easing = !reducedMotion;
  const zoomPct = Math.round((tools.zoom ?? 1) * 100);

  return (
    <div className="absolute right-3 bottom-3 z-10 flex items-center gap-1 rounded-control border border-border bg-surface p-1 mol-motion-fade">
      {editable && (
        <>
          <WorkbenchIconAction label="Undo" onClick={() => ctx.history.undo()}>
            <Undo2 className="size-3.5" />
          </WorkbenchIconAction>
          <WorkbenchIconAction label="Redo" onClick={() => ctx.history.redo()}>
            <Redo2 className="size-3.5" />
          </WorkbenchIconAction>
          <span aria-hidden="true" className="mx-1 h-4 w-px bg-border" />
        </>
      )}
      <WorkbenchIconAction label="Zoom out" onClick={() => tools.zoomout(easing)}>
        <Minus className="size-3.5" />
      </WorkbenchIconAction>
      <span
        aria-live="polite"
        className="min-w-[3.5ch] text-center text-micro tabular-nums text-muted-foreground"
      >
        {zoomPct}%
      </span>
      <WorkbenchIconAction label="Zoom in" onClick={() => tools.zoomin(easing)}>
        <Plus className="size-3.5" />
      </WorkbenchIconAction>
      <WorkbenchIconAction label="Fit to view" onClick={() => tools.fitView(easing)}>
        <Maximize2 className="size-3.5" />
      </WorkbenchIconAction>
    </div>
  );
};

/**
 * flowgram's toJSON() drops each node's own data (config, task type) and each
 * edge's kind; an edited document gets them back from the document it was
 * built from, by id, or saving it cannot rebuild the workflow (L06).
 */
const withOwnData = (edited: FlowgramDocument, source: FlowgramDocument): FlowgramDocument => {
  const nodeData = new Map(source.nodes.map((node) => [node.id, node.data]));
  const edgeOf = new Map(
    source.edges.map((edge) => [`${edge.sourceNodeID}->${edge.targetNodeID}`, edge]),
  );
  return {
    ...edited,
    nodes: edited.nodes.map((node) => ({
      ...node,
      data: { ...(nodeData.get(node.id) ?? {}), ...(node.data ?? {}) } as FlowgramNodeData,
    })),
    edges: edited.edges.map((edge) => {
      const own = edgeOf.get(`${edge.sourceNodeID}->${edge.targetNodeID}`);
      return own ? { ...own, ...edge, kind: edge.kind ?? own.kind } : edge;
    }),
  };
};

/** Publishes the live playground tools to the host (inside the provider). */
const CanvasToolsBridge = ({
  editable,
  onTools,
}: {
  editable: boolean;
  onTools: (tools: CanvasTools) => void;
}): null => {
  const tools = usePlaygroundTools();
  const ctx = useClientContext();
  const easing = !useReducedMotion();
  const toolsRef = useRef(tools);
  toolsRef.current = tools;
  const historyRef = useRef(ctx.history);
  historyRef.current = ctx.history;
  const onToolsRef = useRef(onTools);
  onToolsRef.current = onTools;
  const zoomPercent = Math.round((tools.zoom ?? 1) * 100);
  useEffect(() => {
    onToolsRef.current({
      editable,
      zoomPercent,
      undo: () => historyRef.current.undo(),
      redo: () => historyRef.current.redo(),
      zoomIn: () => toolsRef.current.zoomin(easing),
      zoomOut: () => toolsRef.current.zoomout(easing),
      fit: () => toolsRef.current.fitView(easing),
    });
  }, [editable, zoomPercent, easing]);
  return null;
};

export const FlowgramCanvas = ({
  document,
  onNodeClick,
  editable = false,
  onChange,
  definition = false,
  onTools,
  className,
}: FlowgramCanvasProps): JSX.Element => {
  // Callbacks are reached through refs so they are NOT memo deps: a parent that
  // passes inline handlers (e.g. onNodeClick) would otherwise rebuild
  // `editorProps` on every render — and rebuilding it reloads `initialData` into
  // flowgram, discarding any in-progress node drag. Keep editorProps stable per
  // (document, editable).
  const onNodeClickRef = useRef(onNodeClick);
  onNodeClickRef.current = onNodeClick;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  // False until the mount-time auto-layout passes finish (AutoLayoutOnMount).
  const layoutSettledRef = useRef(false);
  // Epoch ms — ignore dirty signals until this time (residual layout after gate).
  const ignoreDirtyUntilRef = useRef(0);
  // The document the canvas was built from, for `withOwnData`.
  const sourceRef = useRef(document);
  sourceRef.current = document;
  // Visual gate: keep a solid mask up while coarse-grid → dagre still jumps.
  // Ref for dirty tracking; state for the overlay (ref alone cannot re-render).
  const [layoutReady, setLayoutReady] = useState(false);

  const editorProps = useMemo<FreeLayoutProps>(() => {
    // Resolve each edge's status so its colour/animation tracks the run. An edge
    // feeds its target, so it takes the target node's status unless the link
    // itself carries a more specific one. `running` target → flowing animation.
    const nodeStatusById = new Map(document.nodes.map((n) => [n.id, n.data.status ?? "pending"]));
    // An edge is coloured by its status's tone; it flows while that status runs.
    const edgeStatusByKey = new Map<string, { tone: StatusTone; flowing: boolean }>();
    // A definition's links are all neutral: no key resolves, so every line is "ready".
    for (const edge of definition ? [] : document.edges) {
      const explicit = edge.data?.status ?? edge.status;
      const raw =
        explicit && explicit !== "pending" ? explicit : nodeStatusById.get(edge.targetNodeID);
      const spec = statusSpec(raw);
      edgeStatusByKey.set(`${edge.sourceNodeID}->${edge.targetNodeID}`, {
        tone: spec.tone,
        flowing: spec.key === "running",
      });
    }
    const lineStatus = (line: {
      from?: { id?: string };
      to?: { id?: string };
      info?: { from?: string; to?: string };
    }): { tone: StatusTone; flowing: boolean } => {
      const from = line.from?.id ?? line.info?.from;
      const to = line.to?.id ?? line.info?.to;
      return edgeStatusByKey.get(`${from}->${to}`) ?? { tone: "ready", flowing: false };
    };

    return {
      background: true,
      readonly: !editable,
      initialData: document,
      nodeRegistries: [],
      // Arrow colour follows status (default grey, blue while flowing, red on
      // error); `setLineClassName` adds the per-status class the stylesheet uses
      // to recolour the gradient stops by the status's tone.
      lineColor: {
        hidden: "transparent",
        default: "var(--molab-muted-foreground)",
        drawing: "var(--molab-accent)",
        hovered: "var(--molab-accent)",
        selected: "var(--molab-accent)",
        error: "var(--status-failed)",
        flowing: "var(--status-running)",
      },
      isFlowingLine: (_ctx, line) => lineStatus(line).flowing,
      setLineClassName: (_ctx, line) => `molab-edge-${lineStatus(line).tone}`,
      // Generic nodes: flowgram auto-assigns a default input + output port
      // (see free-layout-core) so links connect without a custom registry.
      getNodeDefaultRegistry(type) {
        return { type, meta: {} };
      },
      materials: {
        renderDefaultNode: (props: WorkflowNodeProps) => (
          <WorkflowNodeRenderer node={props.node}>
            <NodeCard onNodeClick={(id) => onNodeClickRef.current?.(id)} />
          </WorkflowNodeRenderer>
        ),
      },
      // History must always be enabled: AutoLayoutOnMount and useClientContext()
      // resolve HistoryService via inversify. With history off, readonly canvases
      // throw "No matching bindings found for serviceIdentifier: HistoryService".
      // Undo chrome stays gated on `editable`; we only need the binding + clear().
      history: { enable: true },
      // Node engine / content-change dirty tracking only in editable mode.
      ...(editable
        ? {
            nodeEngine: { enable: true },
            onContentChange(ctx) {
              // Dirty tracking is history-backed, not "any document mutation":
              // 1) Mount-time auto-layout MOVE_NODEs fire before the dirty gate
              //    opens (AutoLayoutOnMount clears history, then opens the gate).
              // 2) A short post-gate suppress ignores residual layout MOVE_NODEs.
              // 3) After that, only undoable user edits count — if the user
              //    undoes everything, canUndo() is false and we emit null so
              //    the host drops its draft (no false leave-prompt).
              if (!layoutSettledRef.current) return;
              if (Date.now() < ignoreDirtyUntilRef.current) return;
              // A drag is not an edit: positions are laid out on every load.
              const current = ctx.document.toJSON();
              if (!ctx.history.canUndo()) {
                onChangeRef.current?.(null);
                return;
              }
              onChangeRef.current?.(
                withOwnData(current as unknown as FlowgramDocument, sourceRef.current),
              );
            },
          }
        : {}),
      onAllLayersRendered(ctx) {
        ctx.document.fitView(false);
      },
    };
  }, [document, editable, definition]);

  // Per-node display data keyed by id — buildFlowgramDocument already computed
  // role/status/parallel on each node, so just index it for NodeCard lookup.
  const nodeDataById = useMemo(
    () => new Map(document.nodes.map((n) => [n.id, n.data])),
    [document],
  );

  // Read-only drill-down: a SubWorkflow node's expand button opens its inner
  // graph in a dialog. The nested canvas is always read-only, regardless of the
  // outer `editable` (you view inner topology, you don't edit it here).
  const [expanded, setExpanded] = useState<{ taskId: string; inner: TaskGraphJson } | null>(null);
  const innerDocument = useMemo(
    () => (expanded ? buildFlowgramDocument(expanded.inner) : null),
    [expanded],
  );

  return (
    <SubworkflowExpandContext.Provider value={(taskId, inner) => setExpanded({ taskId, inner })}>
      <DefinitionContext.Provider value={definition}>
        <NodeDataContext.Provider value={nodeDataById}>
          <div
            className={`relative h-full w-full ${definition ? "molab-definition" : ""} ${className ?? ""}`}
          >
            <FreeLayoutEditorProvider {...editorProps}>
              {onTools ? <CanvasToolsBridge editable={editable} onTools={onTools} /> : null}
              {/*
                Keep the editor mounted and sized under the mask (opacity only) so
                node ResizeObservers + auto-layout measure real rects. Hiding via
                display:none / unmount would zero sizes and re-trigger the jump.
              */}
              <div
                className={`h-full w-full mol-motion-fade ${layoutReady ? "opacity-100" : "opacity-0"}`}
                aria-hidden={!layoutReady}
              >
                <EditorRenderer />
              </div>
              <AutoLayoutOnMount
                settledRef={layoutSettledRef}
                ignoreDirtyUntilRef={ignoreDirtyUntilRef}
                onVisualReady={() => setLayoutReady(true)}
              />
              {onTools ? null : <FlowgramCanvasControls editable={editable} />}
              {!layoutReady && (
                <div
                  role="status"
                  className="absolute inset-0 z-20 bg-canvas"
                  aria-busy="true"
                  aria-label="Laying out workflow"
                />
              )}
            </FreeLayoutEditorProvider>
          </div>
        </NodeDataContext.Provider>
      </DefinitionContext.Provider>

      <Dialog open={expanded !== null} onOpenChange={(open) => !open && setExpanded(null)}>
        <DialogContent className="flex h-dialog-scroll max-w-5xl flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 font-mono text-body-lg">
              <Layers className="size-icon text-muted-foreground" />
              {expanded?.taskId}
              <span className="text-muted-foreground">· inner workflow</span>
              {expanded?.inner.name && (
                <span className="text-muted-foreground">({expanded.inner.name})</span>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="min-h-0 flex-1">
            {innerDocument && <FlowgramCanvas document={innerDocument} definition={definition} />}
          </div>
        </DialogContent>
      </Dialog>
    </SubworkflowExpandContext.Provider>
  );
};
