import {
  type QueryClient,
  queryOptions,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import {
  experimentsApi,
  projectsApi,
  projectsWsApi,
  runsApi,
  workspaceApi,
  workspacesApi,
} from "@/api";
import {
  buildEmptySnapshot,
  mapAssets,
  mapExperiments,
  mapProjects,
  mapRuns,
  mapWorkflows,
} from "@/app/state/api";
import type { LeftPanelView, ProjectSummary, ServeScope, WorkspaceSnapshot } from "@/app/types";
import { reportStatus } from "@/lib/status-report";
import {
  direntsToTreeNodes,
  getWorkspaceFs,
  mergeTreeChildren,
  setWorkspaceFsRoot,
  treeRootFromListing,
} from "@/lib/workspace-fs";
import type { WorkspacePath } from "@/lib/workspace-path";
import { getWorkspaceQueryScope } from "./workspaceSwitchEvents";
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
export type SnapshotSlice = "workspaces" | "workspaceTree" | "projectsList" | "assets";

/**
 * Data the current rail view actually reads. First paint fetches only this;
 * switching views loads the rest. Experiments/runs still expand on demand.
 */
export const slicesForView = (view: LeftPanelView | undefined): readonly SnapshotSlice[] => {
  switch (view) {
    case "workspace":
      return ["workspaces", "workspaceTree"];
    case "asset":
    case "dashboard": // its explorer lists the workspace's projects
      return ["workspaces", "projectsList"];
    case "knowledge":
    case "runs":
    case "activity":
    case "settings":
      return ["workspaces"];
    default:
      // projects, compare, and unknown rail ids
      return ["workspaces", "projectsList"];
  }
};

const WORKSPACE_TREE_BOOTSTRAP_DEPTH = 2;

const fetchWorkspaceTree = async (): Promise<WorkspaceSnapshot["workspaceRoot"]> => {
  const info = await workspaceApi.getWorkspaceInfo();
  if (info.root) setWorkspaceFsRoot(info.root);
  const fs = getWorkspaceFs();
  return treeRootFromListing(
    fs.root ?? "/",
    await fs.listdir("", { maxDepth: WORKSPACE_TREE_BOOTSTRAP_DEPTH }),
  );
};

const fetchWorkspaces = () => workspacesApi.listWorkspaces();
const fetchServeScope = () => workspaceApi.getServeScope();

/** Experiments and runs that live at a serve root below a project. */
const fetchScopeDescendants = async (
  scope: ServeScope | null,
): Promise<Partial<WorkspaceSnapshot>> => {
  if (!scope || scope.kind === "workspace.root" || scope.kind === "workspace.project") {
    return {};
  }
  if (scope.kind === "workspace.experiment") {
    const raw = await experimentsApi.listExperiments("-");
    const experiments = mapExperiments("", raw);
    const runs = (
      await Promise.all(
        experiments.map(async (experiment) =>
          mapRuns("", experiment.id, await runsApi.listRuns("-", experiment.id)),
        ),
      )
    ).flat();
    return { experiments, runs, workflows: mapWorkflows(experiments, raw) };
  }
  if (scope.kind === "workspace.run") {
    const raw = await runsApi.getRun("-", "-", scope.id);
    return { runs: mapRuns("", "", [raw]) };
  }
  return {};
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
    return mapProjects(await projectsApi.listProjects(), ws.key);
  }
  const perWorkspace = await Promise.all(
    workspaces.map(async (ws) => {
      if (ws.unreachable) return [];
      return mapProjects(await projectsWsApi.listProjects(ws.key), ws.key);
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
      return mapAssets(await projectsApi.listProjectAssets(project.id), project.id);
    }),
  );
  return Array.from(new Map(projectAssets.flat().map((item) => [item.id, item])).values());
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
    case "projectsList": {
      const serveScope = await fetchServeScope();
      const projects = await fetchProjectsList(current.workspaces);
      const descendants = await fetchScopeDescendants(serveScope);
      return { serveScope, projects, ...descendants };
    }
    case "assets":
      return { assets: await fetchAllAssets(activeWorkspaceProjects(current)) };
  }
};

type SliceLoader = (
  current: WorkspaceSnapshot,
  slice: SnapshotSlice,
) => Promise<Partial<WorkspaceSnapshot>>;

const INDEPENDENT_SLICES: readonly SnapshotSlice[] = ["workspaces", "workspaceTree"];

/**
 * Run snapshot slices by dependency level. Workspaces and the file tree
 * start together; projects wait for the workspace list; assets wait
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

  const independent = INDEPENDENT_SLICES.filter((slice) => slices.includes(slice));
  if (independent.length > 0) {
    const patches = await Promise.all(independent.map((slice) => loadSlice(next, slice)));
    const merged = { ...next };
    for (const patch of patches) Object.assign(merged, patch);
    next = merged;
    onProgress?.(next);
  }

  if (slices.includes("projectsList")) {
    next = { ...next, ...(await loadSlice(next, "projectsList")) };
    onProgress?.(next);
  }

  if (slices.includes("assets")) {
    next = { ...next, ...(await loadSlice(next, "assets")) };
    onProgress?.(next);
  }

  return next;
};

export const servedWorkspacesQueryOptions = (scope: string) =>
  queryOptions({
    queryKey: ["workspaces", scope],
    queryFn: fetchWorkspaces,
    staleTime: 30_000,
  });

export const workspaceCatalogQueryOptions = (client: QueryClient, scope: string) =>
  queryOptions({
    queryKey: ["workspace", scope, "catalog"],
    queryFn: async () => {
      // fetchQuery joins any in-flight refresh and honors invalidation; a captured
      // workspaces.data value would race a concurrent served-set refresh.
      const workspaces = await client.fetchQuery(servedWorkspacesQueryOptions(scope));
      const { projects, serveScope, experiments, runs, workflows } = await fetchSlices(
        { ...buildEmptySnapshot(), workspaces },
        ["projectsList"],
      );
      return { projects, serveScope, experiments, runs, workflows };
    },
  });

export const useWorkspaceState = (activeView?: LeftPanelView): WorkspaceState => {
  const client = useQueryClient();
  const scope = getWorkspaceQueryScope();
  const baseKey = useMemo(() => ["workspace", scope] as const, [scope]);
  const slices = slicesForView(activeView);
  // These are user expansion choices. Server payloads live exclusively in Query.
  const [projectIds, setProjectIds] = useState<string[]>([]);
  const [experimentIds, setExperimentIds] = useState<[string, string][]>([]);
  const [dataEpoch, setDataEpoch] = useState(0);
  const workspaces = useQuery(servedWorkspacesQueryOptions(scope));
  const catalogOptions = workspaceCatalogQueryOptions(client, scope);
  const catalog = useQuery({
    ...catalogOptions,
    enabled: slices.includes("projectsList") && workspaces.isSuccess,
  });
  const treeKey = [...baseKey, "tree"];
  const tree = useQuery({
    queryKey: treeKey,
    queryFn: fetchWorkspaceTree,
    enabled: slices.includes("workspaceTree"),
  });
  const assets = useQuery({
    queryKey: [...baseKey, "assets"],
    queryFn: async () => {
      const freshCatalog = await client.fetchQuery(workspaceCatalogQueryOptions(client, scope));
      const served = await client.fetchQuery(servedWorkspacesQueryOptions(scope));
      return fetchAllAssets(
        activeWorkspaceProjects({ ...buildEmptySnapshot(), ...freshCatalog, workspaces: served }),
      );
    },
    enabled: activeView === "asset" && catalog.isSuccess,
  });
  const projectOptions = useCallback(
    (id: string) => ({
      queryKey: [...baseKey, "project", id],
      queryFn: () => experimentsApi.listExperiments(id),
    }),
    [baseKey],
  );
  const experimentOptions = useCallback(
    (projectId: string, experimentId: string) => ({
      queryKey: [...baseKey, "experiment", projectId, experimentId],
      queryFn: () => runsApi.listRuns(projectId, experimentId),
    }),
    [baseKey],
  );
  const projects = useQueries({
    queries: projectIds.map(projectOptions),
    combine: (results) => results.map((query) => ({ data: query.data, error: query.error })),
  });
  const experiments = useQueries({
    queries: experimentIds.map(([projectId, experimentId]) => ({
      ...experimentOptions(projectId, experimentId),
      refetchInterval: (query: {
        state: { data?: Awaited<ReturnType<typeof runsApi.listRuns>> };
      }) => (query.state.data?.some((run) => (run.statusSummary?.active ?? 0) > 0) ? 3000 : false),
      refetchIntervalInBackground: false,
    })),
    combine: (results) => results.map((query) => ({ data: query.data, error: query.error })),
  });
  const snapshot = useMemo(() => {
    const next: WorkspaceSnapshot = {
      ...buildEmptySnapshot(),
      ...catalog.data,
      workspaces: workspaces.data ?? [],
      workspaceRoot: tree.data ?? null,
      assets: assets.data ?? [],
    };
    projectIds.forEach((id, index) => {
      const query = projects[index];
      const ws = next.workspaces.find((item) => item.active)?.key;
      if (query?.data) {
        const mapped = mapExperiments(id, query.data, ws);
        next.experiments = [...next.experiments.filter((item) => item.projectId !== id), ...mapped];
        next.workflows = [
          ...next.workflows.filter((item) => item.projectId !== id),
          ...mapWorkflows(mapped, query.data),
        ];
      }
      next.projects = next.projects.map((item) =>
        item.id === id && (!ws || item.workspaceKey === ws)
          ? {
              ...item,
              experimentCount: query?.data?.length ?? item.experimentCount,
              experimentsError: query?.error?.message,
            }
          : item,
      );
    });
    experimentIds.forEach(([projectId, experimentId], index) => {
      const query = experiments[index];
      const ws = next.workspaces.find((item) => item.active)?.key;
      if (query?.data)
        next.runs = [
          ...next.runs.filter(
            (item) => item.projectId !== projectId || item.experimentId !== experimentId,
          ),
          ...mapRuns(projectId, experimentId, query.data, ws),
        ];
      next.experiments = next.experiments.map((item) =>
        item.id === experimentId && item.projectId === projectId
          ? {
              ...item,
              runCount: query?.data?.length ?? item.runCount,
              runsError: query?.error?.message,
            }
          : item,
      );
    });
    return next;
  }, [
    catalog.data,
    workspaces.data,
    tree.data,
    assets.data,
    projectIds,
    projects,
    experimentIds,
    experiments,
  ]);

  const expandProject = async (id: string): Promise<void> => {
    setProjectIds((ids) => (ids.includes(id) ? ids : [...ids, id]));
    // Query stores the failure for rendering and permits an explicit retry.
    const state = client.getQueryState(projectOptions(id).queryKey);
    if (state?.status === "error" || (state?.status === "success" && !state.isInvalidated)) return;
    await client.fetchQuery(projectOptions(id)).catch(() => undefined);
  };
  const expandExperiment = async (projectId: string, experimentId: string): Promise<void> => {
    setExperimentIds((ids) =>
      ids.some(([p, e]) => p === projectId && e === experimentId)
        ? ids
        : [...ids, [projectId, experimentId]],
    );
    const state = client.getQueryState(experimentOptions(projectId, experimentId).queryKey);
    if (state?.status === "error" || (state?.status === "success" && !state.isInvalidated)) return;
    await client.fetchQuery(experimentOptions(projectId, experimentId)).catch(() => undefined);
  };
  const expandDirectory = async (path: WorkspacePath): Promise<void> => {
    try {
      const directoryKey = [...baseKey, "directory", path];
      const state = client.getQueryState(directoryKey);
      if ((state?.status === "error" || state?.status === "success") && !state.isInvalidated)
        return;
      const children = await client.fetchQuery({
        queryKey: directoryKey,
        queryFn: () => getWorkspaceFs().listdir(path, { maxDepth: 1 }),
        staleTime: 0,
      });
      if (scope !== getWorkspaceQueryScope()) return;
      client.setQueryData<WorkspaceSnapshot["workspaceRoot"]>(treeKey, (root) =>
        root ? mergeTreeChildren(root, path, direntsToTreeNodes(children)) : root,
      );
    } catch (error) {
      reportStatus(error instanceof Error ? error.message : "Could not read directory", "error");
    }
  };
  const refresh = useCallback(() => {
    setDataEpoch((epoch) => epoch + 1);
    void client.cancelQueries().then(() => client.invalidateQueries());
  }, [client]);
  const required = [
    workspaces,
    ...(slices.includes("projectsList") ? [catalog] : []),
    ...(slices.includes("workspaceTree") ? [tree] : []),
    ...(activeView === "asset" ? [assets] : []),
  ];
  return {
    snapshot,
    status: required.some((query) => query.isError)
      ? "error"
      : required.some((query) => query.isPending || query.isFetching)
        ? "loading"
        : "ready",
    error: required.find((query) => query.error)?.error ?? null,
    refresh,
    dataEpoch,
    expandDirectory,
    expandProject: useCallback(expandProject, [client, projectOptions]),
    expandExperiment: useCallback(expandExperiment, [client, experimentOptions]),
    isProjectExpanded: (id) =>
      client.getQueryState(projectOptions(id).queryKey)?.status !== "pending" &&
      client.getQueryState(projectOptions(id).queryKey) !== undefined,
    isExperimentExpanded: (p, e) =>
      client.getQueryState(experimentOptions(p, e).queryKey)?.status !== "pending" &&
      client.getQueryState(experimentOptions(p, e).queryKey) !== undefined,
  };
};
