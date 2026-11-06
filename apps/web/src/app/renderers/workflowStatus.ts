import { groupForStatus, type StatusGroupId } from "@/app/runs/statusGroups";
import type { TaskGraphJson } from "@/plugins/workflow/task-graph-ir";

export interface TaskStatusRollup {
  id: string;
  counts: Record<StatusGroupId, number>;
  total: number;
}

const emptyCounts = (): Record<StatusGroupId, number> => ({
  running: 0,
  pending: 0,
  succeeded: 0,
  failed: 0,
  cancelled: 0,
});

/**
 * Count each task across the latest attempt of every run. A task that has
 * not started counts as queued.
 */
export const rollupTaskStatus = (
  graphs: readonly (TaskGraphJson | null | undefined)[],
): TaskStatusRollup[] => {
  const order: string[] = [];
  const byId = new Map<string, TaskStatusRollup>();
  for (const graph of graphs) {
    for (const task of graph?.task_configs ?? []) {
      let row = byId.get(task.id);
      if (!row) {
        row = { id: task.id, counts: emptyCounts(), total: 0 };
        byId.set(task.id, row);
        order.push(task.id);
      }
      const group = groupForStatus(task.status ?? "pending") ?? "pending";
      row.counts[group] += 1;
      row.total += 1;
    }
  }
  return order.map((id) => byId.get(id) as TaskStatusRollup);
};
