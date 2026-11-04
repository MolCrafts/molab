import { isChemicalStructureName, structureRank } from "@/lib/structure-files";

export interface TaskScalar {
  key: string;
  value: string;
}

export interface TaskStructure {
  key: string;
  label: string;
  path: string;
}

export interface TaskProduct {
  taskId: string;
  status?: string;
  scalars: TaskScalar[];
  structures: TaskStructure[];
}

interface TaskLike {
  id: string;
  status?: string;
  outputs?: Record<string, unknown>;
}

/** Turn an absolute journal path into a path the attempt file API can read. */
export const executionRelativePath = (value: string, executionId: string): string | null => {
  const marker = `/executions/${executionId}/`;
  const at = value.indexOf(marker);
  if (at >= 0) return value.slice(at + marker.length);
  if (value.startsWith("/") || /^[A-Za-z]:[\\/]/.test(value)) return null;
  return value;
};

const scalarText = (value: unknown): string | null => {
  if (typeof value === "string") {
    const text = value.trim();
    if (!text || text.length > 160) return null;
    if (text.includes("/") || text.includes("\\")) return null;
    return text;
  }
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return null;
};

const fileName = (path: string): string => path.split("/").pop() || path;

/** One row per task: its status, short results, and structure files it wrote. */
export const taskProducts = (tasks: readonly TaskLike[], executionId: string): TaskProduct[] => {
  const products: TaskProduct[] = [];
  for (const task of tasks) {
    const scalars: TaskScalar[] = [];
    const structures: TaskStructure[] = [];
    for (const [key, value] of Object.entries(task.outputs ?? {})) {
      if (typeof value === "string") {
        const relative = executionRelativePath(value, executionId);
        if (relative && isChemicalStructureName(relative)) {
          structures.push({ key, label: fileName(relative), path: relative });
          continue;
        }
      }
      const text = scalarText(value);
      if (text !== null) scalars.push({ key, value: text });
    }
    structures.sort(
      (left, right) =>
        structureRank(left.label) - structureRank(right.label) || left.key.localeCompare(right.key),
    );
    if (scalars.length === 0 && structures.length === 0 && !task.status) continue;
    products.push({ taskId: task.id, status: task.status, scalars, structures });
  }
  return products;
};
