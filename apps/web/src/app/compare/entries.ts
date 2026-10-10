/**
 * Building a bag item from the row shapes the UI already has.
 *
 * `workspaceKey` is the one level no row type always carries: the backend
 * answers for whichever workspace the request selected, so only the caller
 * knows which one it asked.
 */

import type { WorkspaceRunRow } from "@/app/runs/types";
import type {
  ExperimentSummary,
  ProjectSummary,
  RunSummary,
  ServedWorkspaceSummary,
} from "@/app/types";

import type { CompareItem } from "./types";

export const activeWorkspace = (
  workspaces: readonly ServedWorkspaceSummary[],
): ServedWorkspaceSummary | null => workspaces.find((ws) => ws.active) ?? workspaces[0] ?? null;

interface Scope {
  workspaceKey: string;
  workspaceLabel: string;
  projectName: string;
  experimentName: string;
}

const nowIso = (): string => new Date().toISOString();

export const itemFromProject = (
  project: ProjectSummary,
  workspace: { key: string; label: string },
): CompareItem => ({
  ref: {
    kind: "project",
    workspaceKey: workspace.key,
    projectId: project.id,
  },
  executionId: null,
  workspaceLabel: workspace.label,
  projectName: project.name,
  experimentName: "",
  runName: "",
  parameters: {},
  category: null,
  addedAt: nowIso(),
});

export const itemFromExperiment = (
  experiment: ExperimentSummary,
  workspace: { key: string; label: string },
  projectName: string,
): CompareItem => ({
  ref: {
    kind: "experiment",
    workspaceKey: workspace.key,
    projectId: experiment.projectId,
    experimentId: experiment.id,
  },
  executionId: null,
  workspaceLabel: workspace.label,
  projectName,
  experimentName: experiment.name,
  runName: "",
  parameters: {},
  category: null,
  addedAt: nowIso(),
});

export const itemFromRunSummary = (run: RunSummary, scope: Scope): CompareItem => ({
  ref: {
    kind: "run",
    workspaceKey: scope.workspaceKey,
    projectId: run.projectId,
    experimentId: run.experimentId,
    runId: run.id,
  },
  executionId: null,
  workspaceLabel: scope.workspaceLabel,
  projectName: scope.projectName,
  experimentName: scope.experimentName,
  runName: run.name,
  parameters: run.parameters ?? {},
  category: null,
  addedAt: nowIso(),
});

export const itemFromWorkspaceRunRow = (
  row: WorkspaceRunRow,
  workspace: { key: string; label: string },
): CompareItem => ({
  ref: {
    kind: "run",
    workspaceKey: workspace.key,
    projectId: row.projectId,
    experimentId: row.experimentId,
    runId: row.id,
  },
  executionId: null,
  workspaceLabel: workspace.label,
  projectName: row.projectName,
  experimentName: row.experimentName,
  runName: row.name,
  parameters: row.parameters ?? {},
  category: null,
  addedAt: nowIso(),
});

/** @deprecated Use itemFromRunSummary — kept for callers that still say "entry". */
export const entryFromRunSummary = itemFromRunSummary;

/** @deprecated Use itemFromWorkspaceRunRow. */
export const entryFromWorkspaceRunRow = itemFromWorkspaceRunRow;
