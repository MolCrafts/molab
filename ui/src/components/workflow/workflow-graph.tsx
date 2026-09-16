/**
 * WorkflowGraph — the inline / plan-preview workflow canvas.
 *
 * Renders a workflow IR as the visual half of an ``exit_plan_mode`` handoff and
 * inside the run "what ran" section: the IR is parsed, lowered to a flowgram
 * free-layout document via {@link buildFlowgramDocument}, and drawn read-only on
 * the same `@flowgram.ai/free-layout-editor` canvas the full viewers use. Node
 * clicks bubble up through the `onNodeClick` prop (RunViewer wires this to the
 * `inspectedTask` → TaskViewer path).
 */

import { type JSX, lazy, Suspense, useMemo } from "react";
import {
  buildFlowgramDocument,
  normalizeTaskGraph,
  parseTaskGraphIr,
} from "@/components/workflow/flowgram-document";
import type { TaskGraphJson } from "@/components/workflow/task-graph-ir";

// Back-compat alias: the inline preview historically spoke of a "WorkflowIR".
// It is now the canonical {@link TaskGraphJson}.
export type WorkflowIR = TaskGraphJson;

/**
 * The flowgram canvas, split out of the entry bundle.
 *
 * `@flowgram.ai/free-layout-editor` drags in inversify and its own CSS — a
 * large dependency that only matters once a graph is actually on screen. Every
 * inline-graph surface reaches the canvas through this module, so deferring the
 * import here is what keeps flowgram out of the initial download for the many
 * screens that never draw a workflow.
 */
const LazyFlowgramCanvas = lazy(async () => ({
  default: (await import("@/components/workflow/flowgram-canvas")).FlowgramCanvas,
}));

/**
 * Parse a serialized workflow IR string into the canonical {@link TaskGraphJson}.
 * Returns `null` when the string is absent, not JSON, or not a
 * `{task_configs, links}` payload — so callers fall back to showing raw text.
 */
export const parseWorkflowIr = parseTaskGraphIr;

interface WorkflowGraphProps {
  ir: TaskGraphJson;
  /** Optional fixed height for the inline render area (default 280px). */
  height?: number;
  className?: string;
  /** Called with the task id when a node is clicked. */
  onNodeClick?: (taskId: string) => void;
}

export const WorkflowGraph = ({
  ir,
  height = 280,
  className,
  onNodeClick,
}: WorkflowGraphProps): JSX.Element => {
  // The IR may arrive in backend field names (task_id / source); normalize.
  const normalized = useMemo(
    () => normalizeTaskGraph(ir as unknown as Record<string, unknown>),
    [ir],
  );
  const document = useMemo(() => buildFlowgramDocument(normalized), [normalized]);
  const invalidLinks = useMemo(() => {
    const known = new Set(document.nodes.map((n) => n.id));
    return normalized.links.filter((link) => !(known.has(link.from) && known.has(link.to)));
  }, [normalized, document]);

  if (document.nodes.length === 0) {
    return (
      <p
        className={
          "rounded-control border border-dashed border-border/60 bg-muted/10 px-3 py-2 text-label italic text-muted-foreground " +
          (className ?? "")
        }
      >
        Empty workflow — no tasks declared.
      </p>
    );
  }

  return (
    <div className={className}>
      <div className="overflow-hidden rounded-control border border-border/60" style={{ height }}>
        <Suspense
          fallback={<div className="mol-motion-progress-pulse h-full w-full bg-muted/20" />}
        >
          <LazyFlowgramCanvas document={document} onNodeClick={onNodeClick} />
        </Suspense>
      </div>
      {invalidLinks.length > 0 && (
        <p className="mt-1 text-micro text-status-warning-foreground">
          {invalidLinks.length} link
          {invalidLinks.length === 1 ? "" : "s"} reference {invalidLinks.length === 1 ? "an" : ""}{" "}
          unknown task {invalidLinks.length === 1 ? "id" : "ids"} and were skipped.
        </p>
      )}
    </div>
  );
};
