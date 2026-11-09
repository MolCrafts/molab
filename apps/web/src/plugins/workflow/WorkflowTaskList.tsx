/**
 * The workflow as a list (Figma L06-8, decision 8): on a phone the canvas is
 * too small to read, so the tasks come in run order — name, type, and what
 * each runs after. A tap previews the task definition (L12).
 */

import { ChevronRight, Workflow } from "lucide-react";
import type { JSX } from "react";
import type { TaskGraphJson } from "./task-graph-ir";

export interface OrderedTask {
  id: string;
  type: string;
  after: string[];
}

/**
 * Tasks in dependency order, one level at a time. A loop has no order: its tasks
 * follow in the graph's own order, so nothing is dropped.
 */
export const taskOrder = (graph: TaskGraphJson): OrderedTask[] => {
  const ids = graph.task_configs.map((task) => task.id);
  const after = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const link of graph.links) {
    const list = after.get(link.to);
    if (list && ids.includes(link.from) && !list.includes(link.from)) list.push(link.from);
  }
  // Level by level, so tasks at the same depth keep the graph's own order.
  const placed: string[] = [];
  const done = new Set<string>();
  for (;;) {
    const level = ids.filter(
      (id) => !done.has(id) && (after.get(id) ?? []).every((dep) => done.has(dep)),
    );
    if (level.length === 0) break;
    for (const id of level) {
      placed.push(id);
      done.add(id);
    }
  }
  const rest = ids.filter((id) => !done.has(id));
  const typeOf = new Map(graph.task_configs.map((task) => [task.id, task.type]));
  return [...placed, ...rest].map((id) => ({
    id,
    type: typeOf.get(id) ?? "",
    after: after.get(id) ?? [],
  }));
};

export const WorkflowTaskList = ({
  graph,
  onPreview,
}: {
  graph: TaskGraphJson;
  onPreview: (taskId: string) => void;
}): JSX.Element => (
  <ol aria-label="Tasks in run order" className="h-full overflow-auto px-4">
    {taskOrder(graph).map((task) => (
      <li key={task.id} className="border-b border-border">
        <button
          type="button"
          onClick={() => onPreview(task.id)}
          className="flex min-h-12 w-full items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring"
        >
          <Workflow aria-hidden className="size-icon shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-body text-foreground">{task.id}</span>
            <span className="block truncate font-mono text-label text-muted-foreground">
              {task.type}
              {task.after.length > 0 ? ` · after ${task.after.join(", ")}` : ""}
            </span>
          </span>
          <ChevronRight aria-hidden className="size-icon shrink-0 text-muted-foreground" />
        </button>
      </li>
    ))}
  </ol>
);
