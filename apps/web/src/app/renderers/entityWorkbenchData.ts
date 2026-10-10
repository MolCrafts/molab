import type {
  AssetSummary,
  ExperimentSummary,
  ProjectSummary,
  RendererSnapshot,
  RunSummary,
  WorkflowSummary,
} from "@/app/types";
import type { TaskGraphJson } from "@/components/workflow/task-graph-ir";
import { countRunStatuses, type RunStatusCounts } from "./dashboardData";

export interface WorkflowRollup {
  exists: boolean;
  taskCount: number;
  linkCount: number;
  parallelGroupCount: number;
}

export interface ExperimentRollup {
  experiment: ExperimentSummary;
  runs: RunSummary[];
  counts: RunStatusCounts;
  workflow: WorkflowSummary | undefined;
  workflowSummary: WorkflowRollup;
}

export interface AttentionItem {
  experiment: ExperimentSummary;
  reason: "failed" | "running" | "missing-workflow" | "empty";
  count: number;
}

export interface ProjectWorkbenchData {
  experiments: ExperimentRollup[];
  runs: RunSummary[];
  counts: RunStatusCounts;
  attention: AttentionItem[];
  recentRuns: RunSummary[];
  assetCount: number;
}

export interface ProjectSnapshotCompleteness {
  /** Authoritative server total, or null when the shallow summary did not report it. */
  experimentCount: number | null;
  /** Sum of authoritative per-experiment totals, or null when any child total is unknown. */
  runCount: number | null;
  experimentsComplete: boolean;
  runsComplete: boolean;
}

export interface ExperimentRunCompleteness {
  runCount: number | null;
  runsComplete: boolean;
}

export interface ParameterAxisSummary {
  key: string;
  values: string[];
  count: number;
}

/** One value of a swept parameter, with the status mix of the runs that used it. */
export interface AxisBucketSummary {
  value: string;
  counts: RunStatusCounts;
}

/** A varying parameter and the outcome of the sweep along it. */
export interface AxisBreakdownSummary {
  key: string;
  buckets: AxisBucketSummary[];
}

export interface ExperimentWorkbenchData {
  counts: RunStatusCounts;
  /** All parameter keys seen across declared space + runs. */
  parameterAxes: ParameterAxisSummary[];
  /**
   * Keys with more than one distinct value — columns on the run list.
   * Keys with a single value are constants (shown once, not per row).
   */
  varyingAxes: ParameterAxisSummary[];
  fixedAxes: ParameterAxisSummary[];
  axisBreakdowns: AxisBreakdownSummary[];
  workflowSummary: WorkflowRollup;
}

/** Split axes by scientific layer: varying (table columns) vs fixed (once). */
export const partitionParameterAxes = (
  axes: ParameterAxisSummary[],
): { varyingAxes: ParameterAxisSummary[]; fixedAxes: ParameterAxisSummary[] } => ({
  varyingAxes: axes.filter((axis) => axis.count > 1),
  fixedAxes: axes.filter((axis) => axis.count === 1),
});

const latestRunTime = (run: RunSummary): number =>
  Date.parse(run.finishedAt ?? run.startedAt ?? run.updatedAt ?? "") || 0;

const reportedCount = (value: number | null | undefined): number | null =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;

/** Distinguish authoritative totals from the lazy client snapshot. Consumers
 * must gate status distributions and rates on the corresponding complete flag. */
export const projectSnapshotCompleteness = (
  project: Pick<ProjectSummary, "experimentCount">,
  experiments: Pick<ExperimentSummary, "runCount">[],
  runs: Pick<RunSummary, "id">[],
): ProjectSnapshotCompleteness => {
  const experimentCount = reportedCount(project.experimentCount);
  const experimentsComplete = experimentCount !== null && experiments.length === experimentCount;
  const childRunCounts = experiments.map((experiment) => reportedCount(experiment.runCount));
  const runCount =
    experimentsComplete && childRunCounts.every((count) => count !== null)
      ? childRunCounts.reduce<number>((total, count) => total + (count ?? 0), 0)
      : null;

  return {
    experimentCount,
    runCount,
    experimentsComplete,
    runsComplete: runCount !== null && runs.length === runCount,
  };
};

export const experimentRunCompleteness = (
  experiment: Pick<ExperimentSummary, "runCount">,
  loadedRunCount: number,
): ExperimentRunCompleteness => {
  const runCount = reportedCount(experiment.runCount);
  return {
    runCount,
    runsComplete: runCount !== null && loadedRunCount === runCount,
  };
};

const stringifyAxisValue = (value: unknown): string => {
  if (Array.isArray(value)) return value.map(stringifyAxisValue).join(", ");
  if (value === null || value === undefined) return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

export const summarizeWorkflowGraph = (
  workflow: Pick<WorkflowSummary, "graph"> | { graph?: TaskGraphJson } | undefined,
): WorkflowRollup => {
  const graph = workflow?.graph;
  const links = graph?.links ?? [];
  return {
    exists: Boolean(graph),
    taskCount: graph?.task_configs.length ?? 0,
    linkCount: links.length,
    parallelGroupCount: links.filter((link) => link.kind === "parallel").length,
  };
};

export const buildProjectWorkbenchData = (
  projectId: string,
  snapshot: Pick<RendererSnapshot, "experiments" | "runs" | "workflows" | "assets">,
  projectAssets: Pick<AssetSummary, "id">[] = snapshot.assets.filter(
    (asset) => asset.projectId === projectId,
  ),
): ProjectWorkbenchData => {
  const experiments = snapshot.experiments.filter(
    (experiment) => experiment.projectId === projectId,
  );
  const runs = snapshot.runs.filter((run) => run.projectId === projectId);
  const rollups = experiments.map((experiment) => {
    const experimentRuns = runs.filter((run) => run.experimentId === experiment.id);
    const workflow = snapshot.workflows.find((item) => item.experimentId === experiment.id);
    return {
      experiment,
      runs: experimentRuns,
      counts: countRunStatuses(experimentRuns),
      workflow,
      workflowSummary: summarizeWorkflowGraph(workflow),
    } satisfies ExperimentRollup;
  });

  const attention: AttentionItem[] = [];
  for (const item of rollups) {
    if (item.counts.failed > 0) {
      attention.push({ experiment: item.experiment, reason: "failed", count: item.counts.failed });
    }
    if (item.counts.running > 0) {
      attention.push({
        experiment: item.experiment,
        reason: "running",
        count: item.counts.running,
      });
    }
    if (!item.workflowSummary.exists) {
      attention.push({ experiment: item.experiment, reason: "missing-workflow", count: 1 });
    }
    if (item.counts.total === 0) {
      attention.push({ experiment: item.experiment, reason: "empty", count: 0 });
    }
  }

  const anomalous = runs.filter((run) => run.status === "failed" || run.status === "running");
  const recentRuns = [...new Map([...anomalous, ...runs].map((run) => [run.id, run])).values()]
    .sort((a, b) => latestRunTime(b) - latestRunTime(a))
    .slice(0, 8);

  return {
    experiments: rollups,
    runs,
    counts: countRunStatuses(runs),
    attention,
    recentRuns,
    assetCount: projectAssets.length,
  };
};

export const buildParameterAxes = (
  experiment: Pick<ExperimentSummary, "parameterSpace">,
  runs: Pick<RunSummary, "parameters">[],
): ParameterAxisSummary[] => {
  const valuesByKey = new Map<string, Set<string>>();
  const ensure = (key: string): Set<string> => {
    const existing = valuesByKey.get(key);
    if (existing) return existing;
    const next = new Set<string>();
    valuesByKey.set(key, next);
    return next;
  };

  for (const [key, value] of Object.entries(experiment.parameterSpace ?? {})) {
    const bucket = ensure(key);
    if (Array.isArray(value)) {
      for (const item of value) bucket.add(stringifyAxisValue(item));
    } else {
      bucket.add(stringifyAxisValue(value));
    }
  }

  for (const run of runs) {
    for (const [key, value] of Object.entries(run.parameters ?? {})) {
      ensure(key).add(stringifyAxisValue(value));
    }
  }

  return [...valuesByKey.entries()].map(([key, values]) => ({
    key,
    values: [...values].filter(Boolean),
    count: values.size,
  }));
};

/** Sweep axes worth drawing: more than one value, few enough to read at a glance. */
const MAX_AXIS_BUCKETS = 12;

const compareAxisValues = (left: string, right: string): number => {
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) return leftNumber - rightNumber;
  return left.localeCompare(right);
};

/**
 * Status mix per value of each varying parameter — "which corner of the sweep
 * failed", which is the decision an experiment overview exists to serve. A
 * declared value with no runs keeps its (empty) bucket: not-yet-run is a fact.
 */
export const buildAxisBreakdowns = (
  runs: RunSummary[],
  axes: ParameterAxisSummary[],
): AxisBreakdownSummary[] =>
  axes
    .filter((axis) => axis.count > 1 && axis.count <= MAX_AXIS_BUCKETS)
    .map((axis) => {
      const byValue = new Map<string, RunSummary[]>(axis.values.map((value) => [value, []]));
      for (const run of runs) {
        const value = stringifyAxisValue(run.parameters?.[axis.key]);
        const bucket = byValue.get(value);
        if (bucket) bucket.push(run);
        else byValue.set(value, [run]);
      }
      return {
        key: axis.key,
        buckets: [...byValue.entries()]
          .sort(([left], [right]) => compareAxisValues(left, right))
          .map(([value, bucketRuns]) => ({ value, counts: countRunStatuses(bucketRuns) })),
      };
    });

export const buildExperimentWorkbenchData = (
  experiment: ExperimentSummary,
  runs: RunSummary[],
  workflow: Pick<WorkflowSummary, "graph"> | undefined,
): ExperimentWorkbenchData => {
  const parameterAxes = buildParameterAxes(experiment, runs);
  const { varyingAxes, fixedAxes } = partitionParameterAxes(parameterAxes);
  return {
    counts: countRunStatuses(runs),
    parameterAxes,
    varyingAxes,
    fixedAxes,
    axisBreakdowns: buildAxisBreakdowns(runs, varyingAxes),
    workflowSummary: summarizeWorkflowGraph(workflow),
  };
};
