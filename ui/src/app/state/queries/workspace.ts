/**
 * Workspace-shell queries: the bootstrap set and the lazy entity hierarchy.
 *
 * Every one of these was a hand-rolled `useState` + `useEffect` + `fetch` in
 * `useWorkspaceState`, fetched **serially** (plan P2 §2b). They are now
 * independent queries, so the four bootstrap calls go out in parallel and a
 * revisit inside `staleTime` issues nothing.
 *
 * Two shapes are exported per entity:
 *  - `xxxQuery(...)` — a plain options object, for `useQueries` over a dynamic
 *    set (the expanded projects / experiments / directories) and for
 *    `prefetchQuery` on hover.
 *  - `useXxxQuery(...)` — the `useQuery` binding for a fixed subscription.
 *
 * Mapping (`mapProjects`, `mapRuns`, …) runs in `select` so it happens once
 * per response rather than once per render, and structural sharing keeps the
 * mapped arrays referentially stable across a no-op refetch.
 */

import {
  type QueryClient,
  queryOptions,
  type UseQueryResult,
  useQuery,
} from "@tanstack/react-query";
import type { TargetResponse } from "@/api/generated/models/TargetResponse";
import { TargetsService } from "@/api/generated/services/TargetsService";
import {
  agentApi,
  mapAgentSessions,
  mapAssets,
  mapExperiments,
  mapProjects,
  mapRuns,
  mapWorkflows,
  workspaceApi,
} from "@/app/state/api";
import type {
  AgentSessionSummary,
  ApiAssetResponse,
  ApiExperimentResponse,
  ApiProjectResponse,
  ApiRunResponse,
  AssetSummary,
  ExperimentSummary,
  ProjectSummary,
  RunSummary,
  ServedWorkspaceSummary,
  WorkflowSummary,
  WorkspaceTreeNode,
} from "@/app/types";
import {
  direntsToTreeNodes,
  getWorkspaceFs,
  treeRootFromListing,
  type WorkspaceDirent,
} from "@/lib/workspace-fs";
import type { WorkspacePath } from "@/lib/workspace-path";
import { type AssetScopeKey, qk } from "./keys";

/** Depth of the one bootstrap listing of the workspace root. */
export const WORKSPACE_TREE_BOOTSTRAP_DEPTH = 2;

/** Server-reported workspace shell info. */
export interface WorkspaceInfo {
  root: string;
  projectCount: number;
  assetCount: number;
  connected?: boolean | null;
  indexed?: boolean | null;
  ready?: boolean | null;
}

/** Experiments plus the workflows derived from the same response. */
export interface ExperimentsSlice {
  experiments: ExperimentSummary[];
  workflows: WorkflowSummary[];
}

// ── Served workspaces ───────────────────────────────────────────────────────

export const workspacesQuery = () =>
  queryOptions({
    queryKey: qk.workspaces(),
    queryFn: (): Promise<ServedWorkspaceSummary[]> => workspaceApi.getServedWorkspaces(),
    staleTime: 60_000,
  });

export const useWorkspacesQuery = (): UseQueryResult<ServedWorkspaceSummary[]> =>
  useQuery(workspacesQuery());

// ── Workspace info ──────────────────────────────────────────────────────────

export const workspaceInfoQuery = () =>
  queryOptions({
    queryKey: qk.info(),
    queryFn: (): Promise<WorkspaceInfo> => workspaceApi.getWorkspaceInfo(),
    staleTime: 60_000,
  });

export const useWorkspaceInfoQuery = (): UseQueryResult<WorkspaceInfo> =>
  useQuery(workspaceInfoQuery());

// ── Workspace file tree ─────────────────────────────────────────────────────

/**
 * One directory listing. `path` is workspace-relative ("" is the root), so
 * this never depends on `GET /workspace/info` having resolved first — that
 * dependency was the old bootstrap's second waterfall step.
 */
export const treeQuery = (path: WorkspacePath, depth: number) =>
  queryOptions({
    queryKey: qk.tree(path, depth),
    queryFn: (): Promise<WorkspaceDirent[]> =>
      getWorkspaceFs().listdir(path, { maxDepth: depth, includeCatalog: true }),
  });

/** The bootstrap root listing, mapped to the snapshot's tree root. */
export const workspaceRootQuery = () =>
  queryOptions({
    ...treeQuery("", WORKSPACE_TREE_BOOTSTRAP_DEPTH),
    select: (children: WorkspaceDirent[]): WorkspaceTreeNode =>
      treeRootFromListing(getWorkspaceFs().root ?? "/", children),
  });

/** A lazily expanded subdirectory, mapped to tree nodes. */
export const treeChildrenQuery = (path: WorkspacePath) =>
  queryOptions({
    ...treeQuery(path, 1),
    select: (children: WorkspaceDirent[]): WorkspaceTreeNode[] => direntsToTreeNodes(children),
  });

// ── Projects ────────────────────────────────────────────────────────────────

export const projectsQuery = () =>
  queryOptions({
    queryKey: qk.projects(),
    queryFn: (): Promise<ApiProjectResponse[]> => workspaceApi.getProjects(),
    select: (rows: ApiProjectResponse[]): ProjectSummary[] => mapProjects(rows),
  });

export const useProjectsQuery = (
  options: { enabled?: boolean } = {},
): UseQueryResult<ProjectSummary[]> =>
  useQuery({ ...projectsQuery(), enabled: options.enabled ?? true });

/** Projects of one named workspace (multi-workspace nav only). */
export const projectsForQuery = (wsKey: string) =>
  queryOptions({
    queryKey: qk.projectsFor(wsKey),
    queryFn: (): Promise<ApiProjectResponse[]> => workspaceApi.getProjectsForWorkspace(wsKey),
    select: (rows: ApiProjectResponse[]): ProjectSummary[] => mapProjects(rows, wsKey),
  });

// ── Experiments ─────────────────────────────────────────────────────────────

export const experimentsQuery = (projectId: string) =>
  queryOptions({
    queryKey: qk.experiments(projectId),
    queryFn: (): Promise<ApiExperimentResponse[]> => workspaceApi.getExperiments(projectId),
    select: (rows: ApiExperimentResponse[]): ExperimentsSlice => {
      const experiments = mapExperiments(projectId, rows);
      return { experiments, workflows: mapWorkflows(experiments, rows) };
    },
  });

export const useExperimentsQuery = (
  projectId: string,
  options: { enabled?: boolean } = {},
): UseQueryResult<ExperimentsSlice> =>
  useQuery({
    ...experimentsQuery(projectId),
    enabled: (options.enabled ?? true) && projectId !== "",
  });

/** One experiment's detail record (dialogs and headers). */
export const useExperimentQuery = (
  projectId: string,
  experimentId: string,
  options: { enabled?: boolean } = {},
): UseQueryResult<ExperimentSummary | null> =>
  useQuery({
    ...experimentsQuery(projectId),
    enabled: (options.enabled ?? true) && projectId !== "" && experimentId !== "",
    select: (rows: ApiExperimentResponse[]): ExperimentSummary | null =>
      mapExperiments(projectId, rows).find((item) => item.id === experimentId) ?? null,
  });

// ── Runs of one experiment ──────────────────────────────────────────────────

export const experimentRunsQuery = (projectId: string, experimentId: string) =>
  queryOptions({
    queryKey: qk.experimentRuns(projectId, experimentId),
    queryFn: (): Promise<ApiRunResponse[]> => workspaceApi.getRuns(projectId, experimentId),
    select: (rows: ApiRunResponse[]): RunSummary[] => mapRuns(projectId, experimentId, rows),
  });

// ── Agent sessions ──────────────────────────────────────────────────────────

export const agentSessionsQuery = () =>
  queryOptions({
    queryKey: qk.agentSessions(),
    queryFn: () => agentApi.listSessions(),
    select: (rows): AgentSessionSummary[] => mapAgentSessions(rows),
  });

export const useAgentSessionsQuery = (): UseQueryResult<AgentSessionSummary[]> =>
  useQuery(agentSessionsQuery());

// ── Assets ──────────────────────────────────────────────────────────────────

/** Raw asset rows for a scope — the shared cache entry both shapes read. */
export const assetsQuery = (scope: AssetScopeKey) =>
  queryOptions({
    queryKey: qk.assets(scope),
    queryFn: (): Promise<ApiAssetResponse[]> =>
      scope.kind === "project" ? workspaceApi.getProjectAssets(scope.id) : workspaceApi.getAssets(),
    staleTime: 60_000,
  });

/** The workspace-wide asset list (asset view only — never on bootstrap). */
export const useAssetsQuery = (
  options: { enabled?: boolean } = {},
): UseQueryResult<AssetSummary[]> =>
  useQuery({
    ...assetsQuery({ kind: "workspace" }),
    enabled: options.enabled ?? true,
    select: (rows: ApiAssetResponse[]): AssetSummary[] => mapAssets(rows),
  });

/** One project's assets, mapped to the snapshot shape. */
export const useProjectAssetsQuery = (
  projectId: string,
  options: { enabled?: boolean } = {},
): UseQueryResult<AssetSummary[]> =>
  useQuery({
    ...assetsQuery({ kind: "project", id: projectId }),
    enabled: (options.enabled ?? true) && projectId !== "",
    select: (rows: ApiAssetResponse[]): AssetSummary[] => mapAssets(rows, projectId),
  });

/**
 * One project's assets as the raw wire rows — `ProjectViewer`'s workbench
 * tables read `ApiAssetResponse` fields directly. Same cache entry as
 * {@link useProjectAssetsQuery}, so the two never double-fetch.
 */
export const useProjectAssetsRawQuery = (projectId: string): UseQueryResult<ApiAssetResponse[]> =>
  useQuery({ ...assetsQuery({ kind: "project", id: projectId }), enabled: projectId !== "" });

// ── Compute targets ─────────────────────────────────────────────────────────

export const targetsQuery = () =>
  queryOptions({
    queryKey: qk.targets(),
    queryFn: async (): Promise<TargetResponse[]> => {
      const response = await TargetsService.listTargetsEndpointApiTargetsGet();
      return response.targets;
    },
    staleTime: 5 * 60_000,
  });

/** Named compute targets — cached so run/experiment dialogs open instantly. */
export const useTargetsQuery = (
  options: { enabled?: boolean } = {},
): UseQueryResult<TargetResponse[]> =>
  useQuery({ ...targetsQuery(), enabled: options.enabled ?? true });

// ── Prefetch helpers (hover/focus intent) ───────────────────────────────────

export const prefetchExperiments = (client: QueryClient, projectId: string): Promise<void> =>
  client.prefetchQuery(experimentsQuery(projectId));

export const prefetchExperimentRuns = (
  client: QueryClient,
  projectId: string,
  experimentId: string,
): Promise<void> => client.prefetchQuery(experimentRunsQuery(projectId, experimentId));

export const prefetchTreeChildren = (client: QueryClient, path: WorkspacePath): Promise<void> =>
  client.prefetchQuery(treeQuery(path, 1));
