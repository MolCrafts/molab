/**
 * Product chrome for one workflow DAG node.
 *
 * Graph engines own drag, ports, and edges. This component owns the node's
 * domain language: role, task type, execution status, validation, and focus.
 */

import { Workflow } from "lucide-react";
import type { JSX, ReactNode } from "react";

import { statusDotClass } from "@/app/components/entity/StatusBadge";
import { canonicalStatusFor } from "@/app/components/entity/status";
import { cn } from "@/lib/utils";

export type WorkflowNodeCanvasRole = "input" | "output" | "task";

export interface WorkflowNodeProps {
  title: string;
  taskType?: string | null;
  status?: string | null;
  canvasRole?: WorkflowNodeCanvasRole;
  subworkflow?: boolean;
  error?: string | null;
  selected?: boolean;
  onActivate?: () => void;
  footer?: ReactNode;
  className?: string;
  density?: "default" | "compact";
}

export const WorkflowNode = ({
  title,
  taskType,
  status,
  canvasRole,
  subworkflow,
  error,
  selected,
  onActivate,
  footer,
  className,
  density,
}: WorkflowNodeProps): JSX.Element => {
  const compact = density === "compact" || Boolean(canvasRole);
  const NodeRoot = onActivate ? "button" : "div";
  const displayStatus = canonicalStatusFor(status);
  const failed = displayStatus === "failed";

  return (
    <NodeRoot
      type={onActivate ? "button" : undefined}
      onClick={onActivate}
      title={error ?? undefined}
      aria-current={selected ? "true" : undefined}
      className={cn(
        "relative w-full rounded-panel border border-border bg-surface text-left shadow-none",
        "transition-[background-color,border-color] duration-(--motion-base) ease-standard",
        compact ? "min-w-40 max-w-64 px-3 py-2" : "min-w-56 max-w-panel-md p-3",
        selected && "border-accent/60 bg-accent/5 ring-1 ring-accent/20",
        onActivate &&
          "cursor-pointer hover:bg-interactive/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        failed && "border-status-failed bg-status-failed-soft hover:bg-status-failed-soft",
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        <span
          className={cn(
            "min-w-0 flex-1 truncate text-body font-medium",
            failed ? "text-status-failed-foreground" : "text-foreground",
          )}
        >
          {title}
        </span>
        {displayStatus && (
          <span
            role="img"
            aria-label={displayStatus}
            title={displayStatus}
            className={cn("size-1.5 flex-none rounded-full", statusDotClass(status))}
          />
        )}
      </div>

      {taskType && (
        <p className="mt-1 truncate font-mono text-micro text-muted-foreground">{taskType}</p>
      )}

      {subworkflow && (
        <div className="mt-2 flex items-center gap-1 text-micro text-muted-foreground">
          <Workflow aria-hidden strokeWidth={1.5} className="size-icon-sm" />
          subflow
        </div>
      )}

      {error && <span className="sr-only">{error}</span>}

      {footer && <div className="mt-2 border-t border-border/70 pt-2">{footer}</div>}
    </NodeRoot>
  );
};
