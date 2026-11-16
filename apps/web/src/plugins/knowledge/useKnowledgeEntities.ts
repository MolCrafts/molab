/**
 * Load the entities a knowledge page names but did not navigate to (L10):
 * the projects that host documents (so a host reads "NVE Drift › Integrator
 * Benchmark", not a path) and the experiments a document references (so its
 * run chips, tables and charts resolve). Same lazy loads as the tree's expand.
 */

import { useEffect } from "react";
import { useEntityExpansion } from "@/app/state/entityExpansion";
import type { RendererSnapshot } from "@/app/types";

const EXPERIMENT_REF = /molab:experiment\/([A-Za-z0-9._-]+)/g;

/** Experiment ids named by `molab:experiment/<id>…` refs in *text*. */
export const referencedExperiments = (text: string): string[] => [
  ...new Set([...text.matchAll(EXPERIMENT_REF)].map((match) => match[1] ?? "").filter(Boolean)),
];

/** Expand every project that hosts one of *hostPaths*. */
export const useHostExpansion = (
  hostPaths: readonly string[],
  snapshot: Pick<RendererSnapshot, "projects">,
): void => {
  const { expandProject, isProjectExpanded } = useEntityExpansion();
  const key = [...new Set(hostPaths)].sort().join("\n");
  useEffect(() => {
    const hosts = key ? key.split("\n") : [];
    for (const project of snapshot.projects) {
      const hosted = hosts.some(
        (host) => host === project.path || host.startsWith(`${project.path}/`),
      );
      if (hosted && !isProjectExpanded(project.id)) expandProject(project.id);
    }
  }, [key, snapshot.projects, expandProject, isProjectExpanded]);
};

/** Expand the experiments *text* references (their runs), once their project is known. */
export const useRefExpansion = (
  text: string,
  snapshot: Pick<RendererSnapshot, "projects" | "experiments">,
): void => {
  const { expandProject, expandExperiment, isProjectExpanded, isExperimentExpanded } =
    useEntityExpansion();
  const ids = referencedExperiments(text).join(",");
  useEffect(() => {
    if (!ids) return;
    const wanted = ids.split(",");
    for (const id of wanted) {
      const experiment = snapshot.experiments.find((row) => row.id === id);
      if (experiment) {
        if (!isExperimentExpanded(experiment.projectId, id)) {
          expandExperiment(experiment.projectId, id);
        }
        continue;
      }
      // Not known yet: load every project's experiments once to find it.
      for (const project of snapshot.projects) {
        if (!isProjectExpanded(project.id)) expandProject(project.id);
      }
    }
  }, [
    ids,
    snapshot.experiments,
    snapshot.projects,
    expandProject,
    expandExperiment,
    isProjectExpanded,
    isExperimentExpanded,
  ]);
};
