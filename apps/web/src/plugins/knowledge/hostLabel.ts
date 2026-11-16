/**
 * Where a knowledge document lives, by name (L10): "Workspace", a project's
 * name, "Project › Experiment", or a run's label. Matched on the server's
 * `path` of each entity; no path is composed.
 */

import { runLabel } from "@/app/runs/runTitle";
import type { RendererSnapshot } from "@/app/types";

export const WORKSPACE_HOST = "Workspace";

export const hostLabel = (
  snapshot: Pick<RendererSnapshot, "projects" | "experiments" | "runs">,
  hostPath: string,
): string => {
  if (!hostPath) return WORKSPACE_HOST;
  const project = snapshot.projects.find((row) => row.path === hostPath);
  if (project) return project.name;
  const experiment = snapshot.experiments.find((row) => row.path === hostPath);
  if (experiment) {
    const parent = snapshot.projects.find((row) => row.id === experiment.projectId);
    return parent ? `${parent.name} › ${experiment.name}` : experiment.name;
  }
  const run = snapshot.runs.find((row) => row.path === hostPath);
  if (run) return runLabel(run);
  // Not loaded in this snapshot: the directory names, without the containers.
  return hostPath
    .split("/")
    .filter((part, index) => !(index % 2 === 0 && /^(projects|experiments|runs)$/.test(part)))
    .join(" › ");
};
