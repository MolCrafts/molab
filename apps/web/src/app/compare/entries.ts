/**
 * Building a `CompareEntry` from the row shapes the UI already has.
 *
 * Runs reach the comparison set from three surfaces with three different row
 * types, and only one of them (`WorkspaceRunRow`) carries its project and
 * experiment names. The adapters here take the names explicitly rather than
 * looking them up, so a caller that already has the snapshot does one pass and
 * a caller that does not is forced to say what it means.
 *
 * `workspaceKey` is the one level no row type carries: the backend answers for
 * whichever workspace the request selected, so only the caller knows which one
 * it asked. Everything downstream depends on it being right.
 */

import type { WorkspaceRunRow } from "@/app/runs/types";
import type { RunSummary, ServedWorkspaceSummary } from "@/app/types";

import type { CompareEntry } from "./types";

/**
 * The workspace whose deep tree is loaded — the one an experiment or run page
 * is showing. Falls back to the only served workspace, then to null.
 */
export const activeWorkspace = (
  workspaces: readonly ServedWorkspaceSummary[],
): ServedWorkspaceSummary | null => workspaces.find((ws) => ws.active) ?? workspaces[0] ?? null;

interface Scope {
  workspaceKey: string;
  workspaceLabel: string;
  projectName: string;
  experimentName: string;
}

/** From an experiment page's run list, where the scope is the page itself. */
export const entryFromRunSummary = (run: RunSummary, scope: Scope): CompareEntry => ({
  ref: {
    workspaceKey: scope.workspaceKey,
    projectId: run.projectId,
    experimentId: run.experimentId,
    runId: run.id,
  },
  selected: true,
  executionId: null,
  workspaceLabel: scope.workspaceLabel,
  projectName: scope.projectName,
  experimentName: scope.experimentName,
  runName: run.name,
  parameters: run.parameters ?? {},
  addedAt: new Date().toISOString(),
});

/**
 * From the workspace-wide runs table, which already carries its own project
 * and experiment names — the row spans experiments, so the page cannot supply
 * them.
 */
export const entryFromWorkspaceRunRow = (
  row: WorkspaceRunRow,
  workspace: { key: string; label: string },
): CompareEntry => ({
  ref: {
    workspaceKey: workspace.key,
    projectId: row.projectId,
    experimentId: row.experimentId,
    runId: row.id,
  },
  selected: true,
  executionId: null,
  workspaceLabel: workspace.label,
  projectName: row.projectName,
  experimentName: row.experimentName,
  runName: row.name,
  parameters: row.parameters ?? {},
  addedAt: new Date().toISOString(),
});
