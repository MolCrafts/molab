import type { KnowledgeClass } from "./knowledgeClass";

/** Initial markdown for a new document. Literature and Note start empty. */
export const DOC_SKELETON: Record<KnowledgeClass, string> = {
  Note: "",
  Literature: "",
  Plan: "## Objective\n\n## Approach\n\n",
  Finding: "## Result\n\n## Evidence\n\n",
  Observation: "## Observation\n\n",
  Report: "## Analysis\n\n",
};

const SOURCED: ReadonlySet<KnowledgeClass> = new Set(["Report", "Finding", "Plan", "Observation"]);

export const isSourcedClass = (cls: KnowledgeClass): boolean => SOURCED.has(cls);

export interface HostRun {
  id: string;
  label: string;
  ref: string;
}

/** Runs that can source a document created on *hostPath*. An empty host is the workspace. */
export const runsForHost = (
  runs: { id: string; name: string; path: string; ref?: string }[],
  hostPath: string,
): HostRun[] =>
  runs.flatMap((run) => {
    if (!run.ref) return [];
    if (hostPath && run.path !== hostPath && !run.path.startsWith(`${hostPath}/`)) return [];
    return [{ id: run.id, label: run.name || run.id, ref: run.ref }];
  });
