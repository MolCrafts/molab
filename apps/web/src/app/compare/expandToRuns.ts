/**
 * Unfolding bag items into the runs the comparison page plots.
 *
 * The explorer snapshot is the children index — not the truncated jobs
 * poller. Completeness is keyed by `(workspaceKey, projectId[, experimentId])`.
 */

import type { ExperimentSummary, RunSummary, WorkspaceSnapshot } from "@/app/types";

import { type CompareEntry, type CompareItem, type CompareRef, itemKey } from "./types";

export class ExpandIncompleteError extends Error {
  readonly ref: CompareRef;

  constructor(ref: CompareRef, message: string) {
    super(message);
    this.name = "ExpandIncompleteError";
    this.ref = ref;
  }
}

const workspaceOf = (row: { workspaceKey?: string }, fallback: string): string =>
  row.workspaceKey ?? fallback;

const experimentsOf = (
  snapshot: WorkspaceSnapshot,
  workspaceKey: string,
  projectId: string,
): ExperimentSummary[] =>
  snapshot.experiments.filter(
    (experiment) =>
      experiment.projectId === projectId && workspaceOf(experiment, workspaceKey) === workspaceKey,
  );

const runsOf = (
  snapshot: WorkspaceSnapshot,
  workspaceKey: string,
  projectId: string,
  experimentId?: string,
): RunSummary[] =>
  snapshot.runs.filter((run) => {
    if (run.projectId !== projectId) return false;
    if (workspaceOf(run, workspaceKey) !== workspaceKey) return false;
    return experimentId === undefined || run.experimentId === experimentId;
  });

const projectLoaded = (
  snapshot: WorkspaceSnapshot,
  ref: Extract<CompareRef, { kind: "project" }>,
): void => {
  const project = snapshot.projects.find(
    (row) => row.id === ref.projectId && workspaceOf(row, ref.workspaceKey) === ref.workspaceKey,
  );
  if (!project) {
    throw new ExpandIncompleteError(
      ref,
      `Project ${ref.projectId} is not in the loaded tree for workspace ${ref.workspaceKey}.`,
    );
  }
  const experiments = experimentsOf(snapshot, ref.workspaceKey, ref.projectId);
  const expected = project.experimentCount;
  if (expected === 0) return;
  if (experiments.length === 0) {
    throw new ExpandIncompleteError(ref, `Experiments under ${ref.projectId} are not loaded.`);
  }
  if (expected != null && experiments.length !== expected) {
    throw new ExpandIncompleteError(
      ref,
      `Experiments under ${ref.projectId} are incomplete (${experiments.length}/${expected}).`,
    );
  }
  for (const experiment of experiments) {
    experimentLoaded(snapshot, {
      kind: "experiment",
      workspaceKey: ref.workspaceKey,
      projectId: ref.projectId,
      experimentId: experiment.id,
    });
  }
};

const experimentLoaded = (
  snapshot: WorkspaceSnapshot,
  ref: Extract<CompareRef, { kind: "experiment" }>,
): void => {
  const experiment = snapshot.experiments.find(
    (row) =>
      row.id === ref.experimentId &&
      row.projectId === ref.projectId &&
      workspaceOf(row, ref.workspaceKey) === ref.workspaceKey,
  );
  if (!experiment) {
    throw new ExpandIncompleteError(
      ref,
      `Experiment ${ref.experimentId} is not in the loaded tree for workspace ${ref.workspaceKey}.`,
    );
  }
  const runs = runsOf(snapshot, ref.workspaceKey, ref.projectId, ref.experimentId);
  const expected = experiment.runCount;
  if (expected === 0) return;
  if (expected != null && runs.length !== expected) {
    throw new ExpandIncompleteError(
      ref,
      `Runs under ${ref.experimentId} are incomplete (${runs.length}/${expected}).`,
    );
  }
  if (expected == null && runs.length === 0) {
    throw new ExpandIncompleteError(ref, `Runs under ${ref.experimentId} are not loaded.`);
  }
};

/** Whether the explorer snapshot has a complete child list for this ancestor. */
export const isSubtreeLoaded = (snapshot: WorkspaceSnapshot, ref: CompareRef): boolean => {
  try {
    if (ref.kind === "project") projectLoaded(snapshot, ref);
    else if (ref.kind === "experiment") experimentLoaded(snapshot, ref);
    return true;
  } catch (error) {
    if (error instanceof ExpandIncompleteError) return false;
    throw error;
  }
};

const experimentNameOf = (
  snapshot: WorkspaceSnapshot,
  workspaceKey: string,
  experimentId: string,
): string =>
  snapshot.experiments.find(
    (experiment) =>
      experiment.id === experimentId && workspaceOf(experiment, workspaceKey) === workspaceKey,
  )?.name ?? experimentId;

const entryFromRun = (
  snapshot: WorkspaceSnapshot,
  run: RunSummary,
  item: CompareItem,
  workspaceKey: string,
): CompareEntry => ({
  ref: {
    workspaceKey,
    projectId: run.projectId,
    experimentId: run.experimentId,
    runId: run.id,
  },
  executionId: item.ref.kind === "run" ? item.executionId : null,
  workspaceLabel: item.workspaceLabel,
  projectName: item.projectName,
  experimentName:
    item.ref.kind === "experiment"
      ? item.experimentName || run.experimentId
      : experimentNameOf(snapshot, workspaceKey, run.experimentId),
  runName: run.name || run.id,
  parameters: run.parameters ?? {},
  addedAt: item.addedAt,
});

/**
 * Unfold bag items into runs, in bag order, first occurrence of a run winning.
 *
 * Throws {@link ExpandIncompleteError} when the explorer snapshot does not
 * hold a complete child list for a project or experiment item.
 */
export const expandToRuns = (
  items: readonly CompareItem[],
  snapshot: WorkspaceSnapshot,
): CompareEntry[] => {
  const out: CompareEntry[] = [];
  const seen = new Set<string>();

  const push = (entry: CompareEntry): void => {
    const key = `${entry.ref.workspaceKey}/${entry.ref.projectId}/${entry.ref.experimentId}/${entry.ref.runId}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push(entry);
  };

  for (const item of items) {
    const { ref } = item;
    if (ref.kind === "run") {
      push({
        ref: {
          workspaceKey: ref.workspaceKey,
          projectId: ref.projectId,
          experimentId: ref.experimentId,
          runId: ref.runId,
        },
        executionId: item.executionId,
        workspaceLabel: item.workspaceLabel,
        projectName: item.projectName,
        experimentName: item.experimentName,
        runName: item.runName,
        parameters: item.parameters,
        addedAt: item.addedAt,
      });
      continue;
    }

    if (ref.kind === "experiment") {
      experimentLoaded(snapshot, ref);
      for (const run of runsOf(snapshot, ref.workspaceKey, ref.projectId, ref.experimentId)) {
        push(entryFromRun(snapshot, run, item, ref.workspaceKey));
      }
      continue;
    }

    projectLoaded(snapshot, ref);
    for (const run of runsOf(snapshot, ref.workspaceKey, ref.projectId)) {
      push(entryFromRun(snapshot, run, item, ref.workspaceKey));
    }
  }

  return out;
};

/**
 * Run-kind bag items for every loaded child of `ancestor`, excluding `exceptKey`.
 *
 * Caller must have already checked {@link isSubtreeLoaded}.
 */
export const siblingRunItems = (
  snapshot: WorkspaceSnapshot,
  ancestor: CompareItem,
  exceptKey: string,
): CompareItem[] => {
  const { ref } = ancestor;
  if (ref.kind === "run") return [];
  const runs =
    ref.kind === "project"
      ? runsOf(snapshot, ref.workspaceKey, ref.projectId)
      : runsOf(snapshot, ref.workspaceKey, ref.projectId, ref.experimentId);
  const now = ancestor.addedAt;
  return runs
    .map((run): CompareItem => {
      const runRef: CompareRef = {
        kind: "run",
        workspaceKey: ref.workspaceKey,
        projectId: run.projectId,
        experimentId: run.experimentId,
        runId: run.id,
      };
      return {
        ref: runRef,
        executionId: null,
        workspaceLabel: ancestor.workspaceLabel,
        projectName: ancestor.projectName,
        experimentName: ref.kind === "experiment" ? ancestor.experimentName : run.experimentId,
        runName: run.name || run.id,
        parameters: run.parameters ?? {},
        category: ancestor.category,
        addedAt: now,
      };
    })
    .filter((item) => itemKey(item.ref) !== exceptKey);
};
