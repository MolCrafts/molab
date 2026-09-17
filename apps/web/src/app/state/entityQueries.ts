import { queryOptions } from "@tanstack/react-query";
import { assetsApi, projectsApi, runsApi } from "@/api";

export const projectKeys = {
  all: ["projects"] as const,
  assets: (projectId: string) => [...projectKeys.all, projectId, "assets"] as const,
};

export const assetKeys = {
  all: ["assets"] as const,
  detail: (projectId: string, assetId: string) =>
    [...assetKeys.all, projectId, assetId, "detail"] as const,
  versions: (projectId: string, assetId: string) =>
    [...assetKeys.all, projectId, assetId, "versions"] as const,
};

export const runKeys = {
  all: ["runs"] as const,
  outputs: (projectId: string, experimentId: string, runId: string, executionId: string) =>
    [...runKeys.all, projectId, experimentId, runId, executionId, "outputs"] as const,
};

export const projectAssetsQueryOptions = (projectId: string) =>
  queryOptions({
    queryKey: projectKeys.assets(projectId),
    queryFn: () => projectsApi.listProjectAssets(projectId),
  });

export const assetDetailQueryOptions = (projectId: string, assetId: string) =>
  queryOptions({
    queryKey: assetKeys.detail(projectId, assetId),
    queryFn: () => assetsApi.getProjectAsset(projectId, assetId),
  });

export const assetVersionsQueryOptions = (projectId: string, assetId: string) =>
  queryOptions({
    queryKey: assetKeys.versions(projectId, assetId),
    queryFn: () => assetsApi.listVersions(projectId, assetId),
  });

export const executionOutputsQueryOptions = (
  projectId: string,
  experimentId: string,
  runId: string,
  executionId: string,
) =>
  queryOptions({
    queryKey: runKeys.outputs(projectId, experimentId, runId, executionId),
    queryFn: () => runsApi.getExecutionOutputs(projectId, experimentId, runId, executionId),
  });
