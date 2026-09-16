/**
 * The workspace shell's data hook — a thin binding over the query cache.
 *
 * Before (plan P2 §2b): four bootstrap slices fetched **serially** in a
 * `for await` loop, an `inflightRef` that silently dropped a concurrent
 * request, and a `refresh()` that emptied `experiments` / `runs` / `workflows`
 * / `assets` from the snapshot and re-ran the whole loop — called from 27
 * sites, so cancelling a run (or merely opening an agent task) collapsed the
 * navigator tree and forced the user to re-expand it one round trip per level.
 *
 * Now: the four bootstrap queries mount independently and go out in parallel;
 * expansion is expressed as membership in a `Set` that drives `useQueries`, so
 * expanding twice costs one request and an already-expanded node re-renders
 * from cache; and `refresh()` is a targeted `invalidateQueries` that leaves
 * both the tree and the data on screen while it revalidates.
 *
 * The exported `WorkspaceState` shape is unchanged (plus `sliceErrors`), so
 * `App` / `AppShell` / the renderers keep compiling against it.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { LeftPanelView, WorkspaceSnapshot } from "@/app/types";
import { setWorkspaceFsRoot } from "@/lib/workspace-fs";
import type { WorkspacePath } from "@/lib/workspace-path";
import { useInvalidate } from "./queries/invalidation";
import {
  EMPTY_SLICE_ERRORS,
  expKey,
  type SliceErrors,
  useWorkspaceSnapshot,
} from "./queries/snapshot";
import { useWorkspaceInfoQuery } from "./queries/workspace";

export type WorkspaceStatus = "idle" | "loading" | "ready" | "error";

export interface WorkspaceState {
  snapshot: WorkspaceSnapshot;
  status: WorkspaceStatus;
  error: Error | null;
  /** Per-slice failures — a failed slice shows an error + Retry, never `[]`. */
  sliceErrors: SliceErrors;
  refresh: () => void;
  /** Lazy-expand a workspace file-tree directory via WorkspaceFs.listdir. */
  expandDirectory: (dirPath: WorkspacePath) => Promise<void>;
  /** Lazy-load experiments under a project (nav expand / open). */
  expandProject: (projectId: string) => Promise<void>;
  /** Lazy-load runs under an experiment (nav expand / open). */
  expandExperiment: (projectId: string, experimentId: string) => Promise<void>;
  /** True when this project's experiments have been fetched. */
  isProjectExpanded: (projectId: string) => boolean;
  /** True when this experiment's runs have been fetched. */
  isExperimentExpanded: (projectId: string, experimentId: string) => boolean;
}

const addTo = (previous: ReadonlySet<string>, value: string): ReadonlySet<string> =>
  previous.has(value) ? previous : new Set(previous).add(value);

export const useWorkspaceState = (activeView?: LeftPanelView): WorkspaceState => {
  // Expansion is *state*, not an imperative fetch: adding an id mounts that
  // node's query. Re-expanding is free, and a manual refresh no longer clears
  // these (the old `refresh()` did, which is what collapsed the tree).
  const [expandedProjects, setExpandedProjects] = useState<ReadonlySet<string>>(new Set());
  const [expandedExperiments, setExpandedExperiments] = useState<ReadonlySet<string>>(new Set());
  const [expandedDirectories, setExpandedDirectories] = useState<ReadonlySet<string>>(new Set());

  const expanded = useMemo(
    () => ({
      projects: expandedProjects,
      experiments: expandedExperiments,
      directories: expandedDirectories,
    }),
    [expandedProjects, expandedExperiments, expandedDirectories],
  );

  const {
    snapshot,
    isPending,
    isFatal,
    fatalError,
    sliceErrors,
    loadedProjects,
    loadedExperiments,
  } = useWorkspaceSnapshot(expanded);

  // Workspace info runs in parallel with the root listing — the old bootstrap
  // awaited it *before* listing, a pure waterfall (`toApiPath("")` needs no root).
  const info = useWorkspaceInfoQuery();
  const infoRoot = info.data?.root;
  useEffect(() => {
    if (infoRoot) setWorkspaceFsRoot(infoRoot);
  }, [infoRoot]);

  const { invalidateView } = useInvalidate();

  const refresh = useCallback((): void => {
    void invalidateView(activeView ?? "workspace");
  }, [invalidateView, activeView]);

  const expandDirectory = useCallback(async (dirPath: WorkspacePath): Promise<void> => {
    setExpandedDirectories((previous) => addTo(previous, dirPath));
  }, []);

  const expandProject = useCallback(async (projectId: string): Promise<void> => {
    setExpandedProjects((previous) => addTo(previous, projectId));
  }, []);

  const expandExperiment = useCallback(
    async (projectId: string, experimentId: string): Promise<void> => {
      setExpandedExperiments((previous) => addTo(previous, expKey(projectId, experimentId)));
    },
    [],
  );

  const isProjectExpanded = useCallback(
    (projectId: string): boolean => loadedProjects.has(projectId),
    [loadedProjects],
  );

  const isExperimentExpanded = useCallback(
    (projectId: string, experimentId: string): boolean =>
      loadedExperiments.has(expKey(projectId, experimentId)),
    [loadedExperiments],
  );

  // Only the first load is "loading": a background revalidation keeps the
  // current data on screen, and the status strip reports it via `useIsFetching`
  // in `App` (scoped to the active view) rather than blanking the shell.
  const status: WorkspaceStatus = isFatal ? "error" : isPending ? "loading" : "ready";

  return {
    snapshot,
    status,
    // Only a total bootstrap failure is fatal (unreachable backend — `App`
    // rethrows it into the route boundary). A single failed slice surfaces
    // through `sliceErrors` with its own retry instead of blanking the app.
    error: fatalError,
    sliceErrors: sliceErrors ?? EMPTY_SLICE_ERRORS,
    refresh,
    expandDirectory,
    expandProject,
    expandExperiment,
    isProjectExpanded,
    isExperimentExpanded,
  };
};
