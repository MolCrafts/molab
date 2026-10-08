/** Index of server `ref` strings for in-app markdown links. */

import { experimentPath, projectPath, runPath } from "@/app/entities/paths";
import type { ExperimentSummary, ProjectSummary, RunSummary } from "@/app/types";
import type { MolabRefTarget } from "@/lib/molab-ref";

export const buildMolabRefIndex = (snapshot: {
  projects: ProjectSummary[];
  experiments: ExperimentSummary[];
  runs: RunSummary[];
}): Map<string, MolabRefTarget> => {
  const index = new Map<string, MolabRefTarget>();
  for (const project of snapshot.projects) {
    if (!project.ref) continue;
    index.set(project.ref, {
      kind: "project",
      label: project.name,
      path: projectPath(project.id),
    });
  }
  for (const experiment of snapshot.experiments) {
    if (!experiment.ref) continue;
    index.set(experiment.ref, {
      kind: "experiment",
      label: experiment.name,
      path: experimentPath(experiment.projectId, experiment.id),
    });
  }
  for (const run of snapshot.runs) {
    if (!run.ref) continue;
    index.set(run.ref, {
      kind: "run",
      label: run.name,
      path: runPath(run.projectId, run.experimentId, run.id),
    });
  }
  return index;
};
