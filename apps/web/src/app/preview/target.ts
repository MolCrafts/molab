/**
 * What the Preview shows (L12). A target is data — ids and the scope that
 * addresses them — never a component or a callback, so two clicks on the same
 * thing compare equal and a target can be opened, copied or re-targeted
 * without knowing who asked. Opening goes through the canonical path builders.
 */

import { experimentPath, projectPath, runPath } from "@/app/entities/paths";
import { getSelectionPath } from "@/app/state/useNavigationState";
import type { FileKind } from "@/app/types";

interface RunScope {
  runId: string;
  projectId: string;
  experimentId: string;
  /** Served workspace the run lives in, when it may not be the active one. */
  workspaceKey?: string;
}

export type PreviewTarget =
  | ({ kind: "run"; label?: string } & RunScope)
  | ({ kind: "attempt"; executionId: string } & RunScope)
  | ({
      kind: "task";
      taskId: string;
      /** The attempt it ran in; the latest when absent. */
      executionId?: string;
    } & RunScope)
  | { kind: "node"; projectId: string; experimentId: string; taskId: string }
  | { kind: "experiment"; projectId: string; experimentId: string }
  | { kind: "project"; projectId: string }
  | { kind: "asset"; assetId: string }
  | { kind: "file"; filePath: string; fileKind: FileKind }
  | { kind: "knowledge"; path: string };

export type PreviewKind = PreviewTarget["kind"];

/** The right overlay peeks at an item inside an italic preview tab, not at the tab itself. */
export const previewOverlaysEditor = (
  target: PreviewTarget | null,
  tab: { key: string; preview?: boolean } | null,
): boolean => Boolean(target && tab?.preview && previewKey(target) !== tab.key);

export const previewKey = (target: PreviewTarget): string => {
  switch (target.kind) {
    case "run":
      return `run:${target.runId}`;
    case "attempt":
      return `attempt:${target.runId}/${target.executionId}`;
    case "task":
      return `task:${target.runId}/${target.taskId}`;
    case "node":
      return `node:${target.experimentId}/${target.taskId}`;
    case "experiment":
      return `experiment:${target.experimentId}`;
    case "project":
      return `project:${target.projectId}`;
    case "asset":
      return `asset:${target.assetId}`;
    case "file":
      return `file:${target.filePath}`;
    case "knowledge":
      return `knowledge:${target.path}`;
  }
};

const NO_SNAPSHOT = { experiments: [], runs: [], workflows: [] };

/** The page a target opens at (↵, ↗, double-click). */
export const previewPath = (target: PreviewTarget): string => {
  switch (target.kind) {
    case "run":
      return runPath(target.projectId, target.experimentId, target.runId);
    case "attempt":
      // ↵ selects the attempt for the page: every view then follows it.
      return runPath(target.projectId, target.experimentId, target.runId, "executions", {
        attempt: target.executionId,
      });
    case "task":
      return `${runPath(target.projectId, target.experimentId, target.runId)}/tasks/${encodeURIComponent(target.taskId)}`;
    case "node":
      return experimentPath(target.projectId, target.experimentId, "workflow");
    case "experiment":
      return experimentPath(target.projectId, target.experimentId);
    case "project":
      return projectPath(target.projectId);
    case "asset":
      return `/assets/${encodeURIComponent(target.assetId)}`;
    case "file":
      return getSelectionPath(
        {
          objectType: "workspace-file",
          objectId: target.filePath,
          filePath: target.filePath,
          fileKind: target.fileKind,
        },
        NO_SNAPSHOT,
      );
    case "knowledge":
      return getSelectionPath({ objectType: "knowledge", objectId: target.path }, NO_SNAPSHOT);
  }
};
