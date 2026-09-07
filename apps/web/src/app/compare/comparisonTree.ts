/**
 * Shaping the staged runs into the tree they actually came from.
 *
 * A flat list of twenty staged runs stops being readable the moment they come
 * from more than one place: `dp=5_seed=1` says nothing about which experiment
 * it belongs to, and folding ancestry into the label (as the chart legend
 * does) spends width to say what nesting says for free. In the panel the width
 * is a panel's, not a legend's, so the ancestry is better spent on structure —
 * project, then experiment, then the run's own parameter name.
 *
 * Order is insertion order at every level: the comparison reads in the order it was
 * built, and staging one more run into an experiment already present does not
 * reorder the tree under the user's cursor.
 *
 * Identity is the ref, never the display name. Two served workspaces may each
 * hold a project called `peo-tg`, so the grouping key carries `workspaceKey`
 * and the ids — merging two projects because they render the same string would
 * silently compare runs from a different machine.
 */

import { type CompareEntry, refKey } from "./types";

export interface ComparisonRunNode {
  /** `refKey(entry.ref)` — the id every mutation on the set is addressed by. */
  key: string;
  entry: CompareEntry;
}

export interface ComparisonExperimentNode {
  id: string;
  name: string;
  runs: ComparisonRunNode[];
}

export interface ComparisonProjectNode {
  id: string;
  name: string;
  workspaceKey: string;
  workspaceLabel: string;
  experiments: ComparisonExperimentNode[];
}

/** NUL cannot occur in an id, so a composed grouping key is unambiguous. */
const compose = (...parts: string[]): string => parts.join("\u0000");

export const buildComparisonTree = (entries: readonly CompareEntry[]): ComparisonProjectNode[] => {
  const projects = new Map<string, ComparisonProjectNode>();
  const experiments = new Map<string, ComparisonExperimentNode>();

  for (const entry of entries) {
    const { workspaceKey, projectId, experimentId } = entry.ref;
    const projectKey = compose(workspaceKey, projectId);
    let project = projects.get(projectKey);
    if (!project) {
      project = {
        id: projectKey,
        name: entry.projectName,
        workspaceKey,
        workspaceLabel: entry.workspaceLabel,
        experiments: [],
      };
      projects.set(projectKey, project);
    }

    const experimentKey = compose(projectKey, experimentId);
    let experiment = experiments.get(experimentKey);
    if (!experiment) {
      experiment = { id: experimentKey, name: entry.experimentName, runs: [] };
      experiments.set(experimentKey, experiment);
      project.experiments.push(experiment);
    }

    experiment.runs.push({ key: refKey(entry.ref), entry });
  }

  return Array.from(projects.values());
};

/**
 * Whether the comparison spans served workspaces.
 *
 * A project name is ambiguous only then; naming the workspace on every row
 * when there is one is noise a 272px panel cannot afford.
 */
export const comparisonSpansWorkspaces = (entries: readonly CompareEntry[]): boolean =>
  new Set(entries.map((entry) => entry.ref.workspaceKey)).size > 1;

export type GroupCheckState = "checked" | "unchecked" | "indeterminate";

/** Tick state of a group, read off the runs under it. */
export const groupCheckState = (runs: readonly ComparisonRunNode[]): GroupCheckState => {
  if (runs.length === 0) return "unchecked";
  const on = runs.filter((run) => run.entry.selected).length;
  if (on === 0) return "unchecked";
  return on === runs.length ? "checked" : "indeterminate";
};

export const runsOfProject = (project: ComparisonProjectNode): ComparisonRunNode[] =>
  project.experiments.flatMap((experiment) => experiment.runs);
