/**
 * Shaping bag items into the Project → Experiment → Run tree for the Selection
 * dock. Group names are the entities themselves, never a user-typed tag.
 *
 * A project or experiment in the bag can expand to the snapshot's children so
 * the dock is the same tree the explorer uses.
 */

import type { WorkspaceSnapshot } from "@/app/types";

import { itemFromRunSummary } from "./entries";
import { type CompareItem, itemKey } from "./types";

export interface ComparisonRunNode {
  key: string;
  entry: CompareItem;
  /** Present because a parent is selected, not because the run is in the bag. */
  virtual?: boolean;
}

export interface ComparisonExperimentNode {
  id: string;
  experimentId: string;
  name: string;
  runs: ComparisonRunNode[];
  virtual?: boolean;
}

export interface ComparisonProjectNode {
  id: string;
  projectId: string;
  name: string;
  workspaceKey: string;
  workspaceLabel: string;
  experiments: ComparisonExperimentNode[];
}

export interface CategoryGroup {
  category: string | null;
  items: CompareItem[];
}

const compose = (...parts: string[]): string => parts.join("\u0000");

export const buildCategoryGroups = (items: readonly CompareItem[]): CategoryGroup[] => {
  const groups: CategoryGroup[] = [];
  const index = new Map<string, CategoryGroup>();
  for (const item of items) {
    const key = item.category ?? "";
    let group = index.get(key);
    if (!group) {
      group = { category: item.category, items: [] };
      index.set(key, group);
      groups.push(group);
    }
    group.items.push(item);
  }
  groups.sort((left, right) => {
    if (left.category === null && right.category !== null) return -1;
    if (left.category !== null && right.category === null) return 1;
    return (left.category ?? "").localeCompare(right.category ?? "");
  });
  return groups;
};

export const buildComparisonTree = (entries: readonly CompareItem[]): ComparisonProjectNode[] => {
  const projects = new Map<string, ComparisonProjectNode>();
  const experiments = new Map<string, ComparisonExperimentNode>();

  for (const entry of entries) {
    const { workspaceKey, projectId } = entry.ref;
    const projectKey = compose(workspaceKey, projectId);
    let project = projects.get(projectKey);
    if (!project) {
      project = {
        id: projectKey,
        projectId,
        name: entry.projectName,
        workspaceKey,
        workspaceLabel: entry.workspaceLabel,
        experiments: [],
      };
      projects.set(projectKey, project);
    }

    if (entry.ref.kind === "project") continue;

    const experimentId = entry.ref.experimentId;
    const experimentKey = compose(projectKey, experimentId);
    let experiment = experiments.get(experimentKey);
    if (!experiment) {
      experiment = {
        id: experimentKey,
        experimentId,
        name: entry.experimentName || experimentId,
        runs: [],
      };
      experiments.set(experimentKey, experiment);
      project.experiments.push(experiment);
    }

    if (entry.ref.kind === "run") {
      experiment.runs.push({ key: itemKey(entry.ref), entry });
    }
  }

  return Array.from(projects.values());
};

export const comparisonSpansWorkspaces = (entries: readonly CompareItem[]): boolean =>
  new Set(entries.map((entry) => entry.ref.workspaceKey)).size > 1;

export const runsOfProject = (project: ComparisonProjectNode): ComparisonRunNode[] =>
  project.experiments.flatMap((experiment) => experiment.runs);

/** Bag keys that sit on this project or anywhere under it. */
export const keysUnderProject = (
  items: readonly CompareItem[],
  project: ComparisonProjectNode,
): string[] =>
  items
    .filter(
      (item) =>
        item.ref.workspaceKey === project.workspaceKey && item.ref.projectId === project.projectId,
    )
    .map((item) => itemKey(item.ref));

/** Bag keys that are this experiment or a run inside it. */
export const keysUnderExperiment = (
  items: readonly CompareItem[],
  project: ComparisonProjectNode,
  experiment: ComparisonExperimentNode,
): string[] =>
  items
    .filter((item) => {
      if (item.ref.kind === "project") return false;
      return (
        item.ref.workspaceKey === project.workspaceKey &&
        item.ref.projectId === project.projectId &&
        item.ref.experimentId === experiment.experimentId
      );
    })
    .map((item) => itemKey(item.ref));

const workspaceOf = (row: { workspaceKey?: string }, fallback: string): string =>
  row.workspaceKey ?? fallback;

/**
 * Fill project / experiment bag items with the snapshot's children so the dock
 * can expand the same hierarchy the explorer shows.
 */
export const hydrateComparisonTree = (
  entries: readonly CompareItem[],
  snapshot: WorkspaceSnapshot,
): ComparisonProjectNode[] => {
  const tree = buildComparisonTree(entries);
  const bagKeys = new Set(entries.map((item) => itemKey(item.ref)));

  for (const project of tree) {
    const projectSelected = entries.some(
      (item) =>
        item.ref.kind === "project" &&
        item.ref.workspaceKey === project.workspaceKey &&
        item.ref.projectId === project.projectId,
    );
    if (projectSelected) {
      const experiments = snapshot.experiments.filter(
        (experiment) =>
          experiment.projectId === project.projectId &&
          workspaceOf(experiment, project.workspaceKey) === project.workspaceKey,
      );
      for (const experiment of experiments) {
        const experimentKey = compose(project.id, experiment.id);
        let node = project.experiments.find((row) => row.experimentId === experiment.id);
        if (!node) {
          node = {
            id: experimentKey,
            experimentId: experiment.id,
            name: experiment.name,
            runs: [],
            virtual: true,
          };
          project.experiments.push(node);
        }
        fillRuns(node, snapshot, project, experiment.name, bagKeys);
      }
      continue;
    }
    for (const experiment of project.experiments) {
      const experimentSelected = entries.some(
        (item) =>
          item.ref.kind === "experiment" &&
          item.ref.workspaceKey === project.workspaceKey &&
          item.ref.projectId === project.projectId &&
          item.ref.experimentId === experiment.experimentId,
      );
      if (experimentSelected) fillRuns(experiment, snapshot, project, experiment.name, bagKeys);
    }
  }
  return tree;
};

const fillRuns = (
  experiment: ComparisonExperimentNode,
  snapshot: WorkspaceSnapshot,
  project: ComparisonProjectNode,
  experimentName: string,
  bagKeys: ReadonlySet<string>,
): void => {
  const known = new Set(experiment.runs.map((run) => run.key));
  const runs = snapshot.runs.filter(
    (run) =>
      run.projectId === project.projectId &&
      run.experimentId === experiment.experimentId &&
      workspaceOf(run, project.workspaceKey) === project.workspaceKey,
  );
  for (const run of runs) {
    const item = itemFromRunSummary(run, {
      workspaceKey: project.workspaceKey,
      workspaceLabel: project.workspaceLabel,
      projectName: project.name,
      experimentName,
    });
    const key = itemKey(item.ref);
    if (known.has(key)) continue;
    experiment.runs.push({ key, entry: item, virtual: !bagKeys.has(key) });
    known.add(key);
  }
};
