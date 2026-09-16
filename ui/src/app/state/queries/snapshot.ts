/**
 * Composes the queries into the `WorkspaceSnapshot` every renderer already
 * reads (plan P2 §2b).
 *
 * This adapter is what makes the migration incremental: the snapshot shape is
 * unchanged, so `LeftPanel`, the viewers and `useNavigationState` keep working
 * untouched while their own pages move to queries page by page.
 *
 * The composition is `useMemo`d on the query **data references**. TanStack's
 * structural sharing keeps those references stable when a refetch returns an
 * equal payload, so a no-op poll re-renders nothing downstream.
 */

import { useQueries, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { buildEmptySnapshot } from "@/app/state/api";
import type {
  ExperimentSummary,
  ProjectSummary,
  RunSummary,
  WorkflowSummary,
  WorkspaceSnapshot,
  WorkspaceTreeNode,
} from "@/app/types";
import { mergeTreeChildren } from "@/lib/workspace-fs";
import type { WorkspacePath } from "@/lib/workspace-path";
import {
  agentSessionsQuery,
  experimentRunsQuery,
  experimentsQuery,
  projectsForQuery,
  projectsQuery,
  treeChildrenQuery,
  workspaceRootQuery,
  workspacesQuery,
} from "./workspace";

/** Which bootstrap slice failed, for per-view error surfaces. */
export interface SliceErrors {
  workspaces: Error | null;
  projects: Error | null;
  tree: Error | null;
  agentSessions: Error | null;
}

export const EMPTY_SLICE_ERRORS: SliceErrors = {
  workspaces: null,
  projects: null,
  tree: null,
  agentSessions: null,
};

export interface ExpansionSets {
  /** Project ids whose experiments are loaded. */
  projects: ReadonlySet<string>;
  /** `projectId/experimentId` keys whose runs are loaded. */
  experiments: ReadonlySet<string>;
  /** Workspace-relative directory paths whose children are loaded. */
  directories: ReadonlySet<string>;
}

export const expKey = (projectId: string, experimentId: string): string =>
  `${projectId}/${experimentId}`;

export const parseExpKey = (key: string): { projectId: string; experimentId: string } => {
  const slash = key.indexOf("/");
  return slash < 0
    ? { projectId: key, experimentId: "" }
    : { projectId: key.slice(0, slash), experimentId: key.slice(slash + 1) };
};

export interface WorkspaceSnapshotResult {
  snapshot: WorkspaceSnapshot;
  /** True until every bootstrap query has settled at least once. */
  isPending: boolean;
  /** True only when every bootstrap query failed (unreachable backend). */
  isFatal: boolean;
  fatalError: Error | null;
  sliceErrors: SliceErrors;
  loadedProjects: ReadonlySet<string>;
  loadedExperiments: ReadonlySet<string>;
}

const errorOf = (error: unknown): Error | null =>
  error instanceof Error ? error : error == null ? null : new Error(String(error));

/**
 * Bootstrap + expansion queries → one snapshot.
 *
 * The four bootstrap queries mount unconditionally and therefore run in
 * parallel; the expansion queries are driven by `expanded`, so adding an id to
 * a set *is* the fetch trigger (no imperative `expandX` call path).
 */
export function useWorkspaceSnapshot(expanded: ExpansionSets): WorkspaceSnapshotResult {
  const workspaces = useQuery(workspacesQuery());
  const root = useQuery(workspaceRootQuery());
  const agentSessions = useQuery(agentSessionsQuery());

  const servedWorkspaces = workspaces.data;
  const multiWorkspace = (servedWorkspaces?.length ?? 0) > 1;

  // Single workspace: the flat route. Several: one query per served workspace.
  const flatProjects = useQuery({ ...projectsQuery(), enabled: !multiWorkspace });
  const perWorkspaceProjects = useQueries({
    queries: multiWorkspace
      ? (servedWorkspaces ?? [])
          .filter((ws) => !ws.unreachable)
          .map((ws) => ({ ...projectsForQuery(ws.key) }))
      : [],
    combine: (results) => ({
      data: results.flatMap((result) => result.data ?? []),
      isPending: results.some((result) => result.isPending),
      error: results.find((result) => result.error)?.error ?? null,
    }),
  });

  const projectList: ProjectSummary[] = multiWorkspace
    ? perWorkspaceProjects.data
    : (flatProjects.data ?? []);
  const projectsPending = multiWorkspace ? perWorkspaceProjects.isPending : flatProjects.isPending;
  const projectsError = multiWorkspace
    ? errorOf(perWorkspaceProjects.error)
    : errorOf(flatProjects.error);

  // ── Expansion: experiments per expanded project ──────────────────────────
  const projectIds = useMemo(() => [...expanded.projects].sort(), [expanded.projects]);
  const experimentResults = useQueries({
    queries: projectIds.map((projectId) => ({ ...experimentsQuery(projectId) })),
    combine: (results) => {
      const experiments: ExperimentSummary[] = [];
      const workflows: WorkflowSummary[] = [];
      const loaded = new Set<string>();
      results.forEach((result, index) => {
        if (!result.data) return;
        experiments.push(...result.data.experiments);
        workflows.push(...result.data.workflows);
        const id = projectIds[index];
        if (id !== undefined) loaded.add(id);
      });
      return { experiments, workflows, loaded: loaded as ReadonlySet<string> };
    },
  });

  // ── Expansion: runs per expanded experiment ──────────────────────────────
  const experimentKeys = useMemo(() => [...expanded.experiments].sort(), [expanded.experiments]);
  const runResults = useQueries({
    queries: experimentKeys.map((key) => {
      const { projectId, experimentId } = parseExpKey(key);
      return { ...experimentRunsQuery(projectId, experimentId) };
    }),
    combine: (results) => {
      const runs: RunSummary[] = [];
      const loaded = new Set<string>();
      results.forEach((result, index) => {
        if (!result.data) return;
        runs.push(...result.data);
        const key = experimentKeys[index];
        if (key !== undefined) loaded.add(key);
      });
      return { runs, loaded: loaded as ReadonlySet<string> };
    },
  });

  // ── Expansion: lazily listed directories, merged into the tree root ──────
  const dirPaths = useMemo(() => [...expanded.directories].sort(), [expanded.directories]);
  const dirResults = useQueries({
    queries: dirPaths.map((path) => ({ ...treeChildrenQuery(path as WorkspacePath) })),
    combine: (results) => results.map((result) => result.data),
  });

  const workspaceRoot: WorkspaceTreeNode | null = useMemo(() => {
    let next = root.data ?? null;
    if (!next) return null;
    dirPaths.forEach((path, index) => {
      const children = dirResults[index];
      if (children) next = mergeTreeChildren(next as WorkspaceTreeNode, path, children);
    });
    return next;
  }, [root.data, dirPaths, dirResults]);

  const snapshot: WorkspaceSnapshot = useMemo(
    () => ({
      ...buildEmptySnapshot(),
      workspaces: servedWorkspaces ?? [],
      projects: projectList,
      experiments: experimentResults.experiments,
      workflows: experimentResults.workflows,
      runs: runResults.runs,
      agentSessions: agentSessions.data ?? [],
      workspaceRoot,
    }),
    [
      servedWorkspaces,
      projectList,
      experimentResults.experiments,
      experimentResults.workflows,
      runResults.runs,
      agentSessions.data,
      workspaceRoot,
    ],
  );

  const sliceErrors: SliceErrors = useMemo(
    () => ({
      workspaces: errorOf(workspaces.error),
      projects: projectsError,
      tree: errorOf(root.error),
      agentSessions: errorOf(agentSessions.error),
    }),
    [workspaces.error, projectsError, root.error, agentSessions.error],
  );

  const isPending =
    workspaces.isPending || projectsPending || root.isPending || agentSessions.isPending;
  const failures = [
    sliceErrors.workspaces,
    sliceErrors.projects,
    sliceErrors.tree,
    sliceErrors.agentSessions,
  ];
  const isFatal = failures.every((error) => error !== null);

  return {
    snapshot,
    isPending,
    isFatal,
    fatalError: isFatal ? failures[0] : null,
    sliceErrors,
    loadedProjects: experimentResults.loaded,
    loadedExperiments: runResults.loaded,
  };
}
