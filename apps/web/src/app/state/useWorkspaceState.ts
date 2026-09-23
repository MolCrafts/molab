import { useCallback, useEffect, useRef, useState } from "react";
import {
  experimentsApi,
  projectsApi,
  projectsWsApi,
  runsApi,
  workspaceApi,
  workspacesApi,
} from "@/api";
import {
  agentApi,
  buildEmptySnapshot,
  mapAgentSessions,
  mapAssets,
  mapExperiments,
  mapProjects,
  mapRuns,
  mapWorkflows,
} from "@/app/state/api";
import { pulseSync } from "@/app/state/syncPulse";
import type {
  LeftPanelView,
  ProjectSummary,
  WorkspaceSnapshot,
  WorkspaceTreeNode,
} from "@/app/types";
import {
  direntsToTreeNodes,
  getWorkspaceFs,
  mergeTreeChildren,
  setWorkspaceFsRoot,
  treeRootFromListing,
} from "@/lib/workspace-fs";
import type { WorkspacePath } from "@/lib/workspace-path";
export type WorkspaceStatus = "idle" | "loading" | "ready" | "error";

export interface WorkspaceState {
  snapshot: WorkspaceSnapshot;
  status: WorkspaceStatus;
  error: Error | null;
  refresh: () => void;
  /**
   * Bumps on every manual refresh after entity caches are cleared. TreeView
   * re-requests lazy loads for folders that stayed open (empty childCount alone
   * does not change when the row was already "Loading…").
   */
  dataEpoch: number;
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

// Slice = an independently fetchable chunk of the snapshot.
// Entity hierarchy (experiments / runs) is **not** a slice — it loads on expand.
export type SnapshotSlice =
  | "workspaces"
  | "workspaceTree"
  | "projectsList"
  | "assets"
  | "agentSessions";

/**
 * Data the current rail view actually reads. First paint fetches only this;
 * switching views loads the rest. Experiments/runs still expand on demand.
 */
export const slicesForView = (view: LeftPanelView | undefined): readonly SnapshotSlice[] => {
  switch (view) {
    case "workspace":
      return ["workspaces", "workspaceTree"];
    case "asset":
      return ["workspaces", "projectsList"];
    case "agent":
      return ["workspaces", "agentSessions"];
    case "knowledge":
    case "runs":
    case "dashboard":
    case "activity":
    case "settings":
      return ["workspaces"];
    default:
      // projects, compare, and unknown rail ids
      return ["workspaces", "projectsList"];
  }
};

const WORKSPACE_TREE_BOOTSTRAP_DEPTH = 2;

const expKey = (projectId: string, experimentId: string): string => `${projectId}/${experimentId}`;

const fetchWorkspaceTree = async (): Promise<WorkspaceSnapshot["workspaceRoot"]> => {
  try {
    try {
      const info = await workspaceApi.getWorkspaceInfo();
      if (info.root) {
        setWorkspaceFsRoot(info.root);
      }
    } catch {
      // optional
    }
    const fs = getWorkspaceFs();
    const children = await fs.listdir("", {
      maxDepth: WORKSPACE_TREE_BOOTSTRAP_DEPTH,
      // Catalog enrichment scans every run/execution for assets.json — seconds
      // on a real lab, and depth-2 from the workspace root has no asset files.
    });
    return treeRootFromListing(fs.root ?? "/", children);
  } catch (err) {
    console.warn("Workspace tree unavailable:", err);
    return null;
  }
};

const findTreeNode = (root: WorkspaceTreeNode, path: string): WorkspaceTreeNode | null => {
  if (root.path === path) return root;
  for (const child of root.children) {
    if (child.path === path) return child;
    if (child.kind === "directory" && path.startsWith(`${child.path}/`)) {
      const hit = findTreeNode(child, path);
      if (hit) return hit;
    }
  }
  return null;
};

const fetchWorkspaces = async (): Promise<WorkspaceSnapshot["workspaces"]> => {
  try {
    return await workspacesApi.listWorkspaces();
  } catch {
    // Soft: list endpoint failed (backend down). Empty set; no console spam.
    return [];
  }
};

const fetchProjectsList = async (
  workspaces: WorkspaceSnapshot["workspaces"],
): Promise<ProjectSummary[]> => {
  // Always stamp workspaceKey so the multi-workspace nav filter
  // (`project.workspaceKey === ws.key`) never drops a single-ws project.
  if (workspaces.length === 0) {
    return mapProjects(await projectsApi.listProjects());
  }
  if (workspaces.length === 1) {
    const ws = workspaces[0];
    if (ws.unreachable) return [];
    try {
      // Prefer flat /api/projects (active workspace) — same data, one RTT.
      return mapProjects(await projectsApi.listProjects(), ws.key);
    } catch {
      return [];
    }
  }
  const perWorkspace = await Promise.all(
    workspaces.map(async (ws) => {
      if (ws.unreachable) return [];
      try {
        return mapProjects(await projectsWsApi.listProjects(ws.key), ws.key);
      } catch {
        return [];
      }
    }),
  );
  return perWorkspace.flat();
};

const activeWorkspaceProjects = (snapshot: WorkspaceSnapshot): ProjectSummary[] => {
  if (snapshot.workspaces.length <= 1) return snapshot.projects;
  const activeKey = snapshot.workspaces.find((ws) => ws.active)?.key;
  return snapshot.projects.filter((project) => project.workspaceKey === activeKey);
};

const fetchAllAssets = async (projects: ProjectSummary[]): Promise<WorkspaceSnapshot["assets"]> => {
  const projectAssets = await Promise.all(
    projects.map(async (project) => {
      try {
        return mapAssets(await projectsApi.listProjectAssets(project.id), project.id);
      } catch (err) {
        console.warn(`Failed to fetch assets for project ${project.id}:`, err);
        return [];
      }
    }),
  );
  return Array.from(new Map(projectAssets.flat().map((item) => [item.id, item])).values());
};

const fetchAgentSessionsList = async (): Promise<WorkspaceSnapshot["agentSessions"]> => {
  try {
    return mapAgentSessions(await agentApi.listSessions());
  } catch (err) {
    console.warn("Agent sessions unavailable:", err);
    return [];
  }
};

const applySlicePatch = async (
  current: WorkspaceSnapshot,
  slice: SnapshotSlice,
): Promise<Partial<WorkspaceSnapshot>> => {
  switch (slice) {
    case "workspaces":
      return { workspaces: await fetchWorkspaces() };
    case "workspaceTree":
      return { workspaceRoot: await fetchWorkspaceTree() };
    case "projectsList":
      return { projects: await fetchProjectsList(current.workspaces) };
    case "assets":
      return { assets: await fetchAllAssets(activeWorkspaceProjects(current)) };
    case "agentSessions":
      return { agentSessions: await fetchAgentSessionsList() };
  }
};

type SliceLoader = (
  current: WorkspaceSnapshot,
  slice: SnapshotSlice,
) => Promise<Partial<WorkspaceSnapshot>>;

const INDEPENDENT_SLICES: readonly SnapshotSlice[] = [
  "workspaces",
  "workspaceTree",
  "agentSessions",
];

/**
 * Run snapshot slices by dependency level. Workspaces, file tree, and agent
 * sessions start together; projects wait for the workspace list; assets wait
 * for the resulting project list. Patches are merged in descriptor order so
 * network completion order cannot make the snapshot nondeterministic.
 */
export const fetchSlices = async (
  current: WorkspaceSnapshot,
  slices: readonly SnapshotSlice[],
  onProgress?: (next: WorkspaceSnapshot) => void,
  loadSlice: SliceLoader = applySlicePatch,
): Promise<WorkspaceSnapshot> => {
  let next = current;

  const loadSafe = async (
    snapshot: WorkspaceSnapshot,
    slice: SnapshotSlice,
  ): Promise<Partial<WorkspaceSnapshot>> => {
    try {
      return await loadSlice(snapshot, slice);
    } catch (err) {
      console.warn(`Snapshot slice "${slice}" failed:`, err);
      return {};
    }
  };

  const independent = INDEPENDENT_SLICES.filter((slice) => slices.includes(slice));
  if (independent.length > 0) {
    const patches = await Promise.all(independent.map((slice) => loadSafe(next, slice)));
    const merged = { ...next };
    for (const patch of patches) Object.assign(merged, patch);
    next = merged;
    onProgress?.(next);
  }

  if (slices.includes("projectsList")) {
    next = { ...next, ...(await loadSafe(next, "projectsList")) };
    onProgress?.(next);
  }

  if (slices.includes("assets")) {
    next = { ...next, ...(await loadSafe(next, "assets")) };
    onProgress?.(next);
  }

  return next;
};

export const useWorkspaceState = (activeView?: LeftPanelView): WorkspaceState => {
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot>(buildEmptySnapshot());
  const [status, setStatus] = useState<WorkspaceStatus>("idle");
  const [error, setError] = useState<Error | null>(null);
  const inflightRef = useRef(false);
  const queuedSlicesRef = useRef<SnapshotSlice[]>([]);
  const loadedSlicesRef = useRef(new Set<SnapshotSlice>());
  const snapshotRef = useRef(snapshot);
  snapshotRef.current = snapshot;

  // On-demand load tracking (entity tree). Cleared on full refresh, then
  // re-populated by re-expanding whatever was open.
  const projectsLoadedRef = useRef(new Set<string>());
  const experimentsLoadedRef = useRef(new Set<string>());
  // In-flight guards so a stuck "Loading…" re-trigger (TreeView still open
  // after refresh) does not fan out duplicate remote requests.
  const projectsLoadingRef = useRef(new Set<string>());
  const experimentsLoadingRef = useRef(new Set<string>());
  const assetsLoadedForViewRef = useRef(false);
  // Force re-render when expand sets flip without snapshot change shape.
  const [, bump] = useState(0);
  const [dataEpoch, setDataEpoch] = useState(0);

  const runFetch = useCallback(
    (slices: readonly SnapshotSlice[], silent: boolean, force = false): Promise<void> => {
      const needed = force
        ? [...slices]
        : slices.filter((slice) => !loadedSlicesRef.current.has(slice));
      if (needed.length === 0) return Promise.resolve();
      if (inflightRef.current) {
        for (const slice of needed) {
          if (!queuedSlicesRef.current.includes(slice)) queuedSlicesRef.current.push(slice);
        }
        return Promise.resolve();
      }
      inflightRef.current = true;
      if (!silent) setStatus("loading");

      const drain = async (): Promise<void> => {
        let batch = needed;
        try {
          while (batch.length > 0) {
            const nextSnapshot = await fetchSlices(snapshotRef.current, batch, (partial) => {
              snapshotRef.current = partial;
              setSnapshot(partial);
              if (!silent) pulseSync();
            });
            snapshotRef.current = nextSnapshot;
            setSnapshot(nextSnapshot);
            for (const slice of batch) loadedSlicesRef.current.add(slice);
            batch = queuedSlicesRef.current.splice(0);
            if (!force) {
              batch = batch.filter((slice) => !loadedSlicesRef.current.has(slice));
            }
          }
          setStatus("ready");
          setError(null);
        } catch (err) {
          setError(err instanceof Error ? err : new Error(String(err)));
          setStatus((prev) => (prev === "ready" ? "ready" : "error"));
        } finally {
          inflightRef.current = false;
          pulseSync();
        }
      };
      return drain();
    },
    [],
  );

  const expandDirectory = useCallback(async (dirPath: WorkspacePath): Promise<void> => {
    const root = snapshotRef.current.workspaceRoot;
    if (!root) return;
    const node = findTreeNode(root, dirPath);
    if (node?.kind !== "directory") return;
    // Skip only when we already have a non-empty listing. An empty
    // ``childrenLoaded`` folder may be a stale remote pin (UI shows "Empty"
    // forever if we refuse to re-listdir).
    if (node.childrenLoaded && node.children.length > 0) return;

    try {
      const fs = getWorkspaceFs();
      const children = await fs.listdir(dirPath, { maxDepth: 1 });
      const childNodes = direntsToTreeNodes(children);
      const nextRoot = mergeTreeChildren(root, dirPath, childNodes);
      const next = { ...snapshotRef.current, workspaceRoot: nextRoot };
      snapshotRef.current = next;
      setSnapshot(next);
    } catch (err) {
      console.warn(`expandDirectory(${dirPath}) failed:`, err);
    }
  }, []);

  const expandProject = useCallback(
    async (projectId: string, options?: { force?: boolean }): Promise<void> => {
      // force=true: re-fetch while keeping current children on screen (SWR).
      if (!options?.force && projectsLoadedRef.current.has(projectId)) return;
      if (projectsLoadingRef.current.has(projectId)) return;
      projectsLoadingRef.current.add(projectId);
      try {
        const raw = await experimentsApi.listExperiments(projectId);
        const workspaceKey = snapshotRef.current.projects.find(
          (p) => p.id === projectId,
        )?.workspaceKey;
        const mapped = mapExperiments(projectId, raw, workspaceKey);
        // Workflows for just these experiments (IR if present on the wire).
        const workflows = mapWorkflows(mapped, raw);
        projectsLoadedRef.current.add(projectId);
        setSnapshot((prev) => {
          const otherExps = prev.experiments.filter((e) => e.projectId !== projectId);
          const otherWfs = prev.workflows.filter((w) => w.projectId !== projectId);
          const next: WorkspaceSnapshot = {
            ...prev,
            experiments: [...otherExps, ...mapped],
            workflows: [...otherWfs, ...workflows],
            // Keep project chip in sync once we know the true exp count.
            projects: prev.projects.map((p) =>
              p.id === projectId ? { ...p, experimentCount: mapped.length } : p,
            ),
          };
          snapshotRef.current = next;
          return next;
        });
        bump((n) => n + 1);
      } catch (err) {
        console.warn(`expandProject(${projectId}) failed:`, err);
        // Fail closed as "loaded" so the row leaves "Loading…" rather than
        // spinning forever; a later refresh re-attempts via force.
        projectsLoadedRef.current.add(projectId);
        bump((n) => n + 1);
      } finally {
        projectsLoadingRef.current.delete(projectId);
      }
    },
    [],
  );

  const expandExperiment = useCallback(
    async (
      projectId: string,
      experimentId: string,
      options?: { force?: boolean },
    ): Promise<void> => {
      const key = expKey(projectId, experimentId);
      if (!options?.force && experimentsLoadedRef.current.has(key)) return;
      if (experimentsLoadingRef.current.has(key)) return;
      experimentsLoadingRef.current.add(key);
      try {
        const raw = await runsApi.listRuns(projectId, experimentId);
        const workspaceKey =
          snapshotRef.current.experiments.find(
            (experiment) => experiment.id === experimentId && experiment.projectId === projectId,
          )?.workspaceKey ??
          snapshotRef.current.projects.find((p) => p.id === projectId)?.workspaceKey;
        const mapped = mapRuns(projectId, experimentId, raw, workspaceKey);
        // Mark loaded only after success — so emptyChildLabel stays "Loading…"
        // rather than "No runs" while the remote fetch is in flight (first open).
        experimentsLoadedRef.current.add(key);
        setSnapshot((prev) => {
          const other = prev.runs.filter(
            (r) => !(r.projectId === projectId && r.experimentId === experimentId),
          );
          // Stamp runCount so the right-side chip flips from "…" to "N run".
          const experiments = prev.experiments.map((e) =>
            e.projectId === projectId && e.id === experimentId
              ? { ...e, runCount: mapped.length }
              : e,
          );
          const next: WorkspaceSnapshot = {
            ...prev,
            experiments,
            runs: [...other, ...mapped],
          };
          snapshotRef.current = next;
          return next;
        });
        bump((n) => n + 1);
      } catch (err) {
        console.warn(`expandExperiment(${key}) failed:`, err);
        experimentsLoadedRef.current.add(key);
        bump((n) => n + 1);
      } finally {
        experimentsLoadingRef.current.delete(key);
      }
    },
    [],
  );

  const refresh = useCallback((): void => {
    // Stale-while-revalidate for the entity tree:
    // keep experiments / runs / workflows on screen, re-fetch open folders in
    // the background, then swap rows in place. Wiping first caused a visible
    // "Loading…" flash even when data came back quickly.
    const reopenProjects = [...projectsLoadedRef.current];
    const reopenExperiments = [...experimentsLoadedRef.current];
    const hadAssets = assetsLoadedForViewRef.current;
    assetsLoadedForViewRef.current = false;
    // Clear in-flight so a stuck load does not block the forced re-fetch.
    projectsLoadingRef.current.clear();
    experimentsLoadingRef.current.clear();
    // Help any open row still on empty/"Loading…" (never successfully loaded).
    setDataEpoch((n) => n + 1);

    const refreshSlices: SnapshotSlice[] = [
      ...new Set([...loadedSlicesRef.current, ...slicesForView(activeView)]),
    ];
    void runFetch(refreshSlices, false, true).then(() => {
      const reloads: Promise<void>[] = [
        ...reopenProjects.map((projectId) => expandProject(projectId, { force: true })),
        ...reopenExperiments.map((key) => {
          const slash = key.indexOf("/");
          if (slash <= 0) return Promise.resolve();
          const projectId = key.slice(0, slash);
          const experimentId = key.slice(slash + 1);
          if (!projectId || !experimentId) return Promise.resolve();
          return expandExperiment(projectId, experimentId, { force: true });
        }),
      ];
      if (hadAssets || activeView === "asset") {
        assetsLoadedForViewRef.current = true;
        reloads.push(runFetch(["assets"], true));
      }
      void Promise.all(reloads);
    });
  }, [runFetch, expandProject, expandExperiment, activeView]);

  const isProjectExpanded = useCallback(
    (projectId: string): boolean => projectsLoadedRef.current.has(projectId),
    // `bump` re-renders consumers; the callback reads the live ref.
    [],
  );

  const isExperimentExpanded = useCallback(
    (projectId: string, experimentId: string): boolean =>
      experimentsLoadedRef.current.has(expKey(projectId, experimentId)),
    [],
  );

  // First paint: only the current view. Switching views fills in the rest.
  useEffect(() => {
    const silent = loadedSlicesRef.current.size > 0;
    void runFetch(slicesForView(activeView), silent);
  }, [activeView, runFetch]);

  // Assets: load once when entering the asset view (not on every poll).
  useEffect(() => {
    if (activeView !== "asset") return;
    if (assetsLoadedForViewRef.current) return;
    assetsLoadedForViewRef.current = true;
    void runFetch(["assets"], true);
  }, [activeView, runFetch]);

  return {
    snapshot,
    status,
    error,
    refresh,
    dataEpoch,
    expandDirectory,
    expandProject,
    expandExperiment,
    isProjectExpanded,
    isExperimentExpanded,
  };
};
