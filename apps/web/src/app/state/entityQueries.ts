import { queryOptions } from "@tanstack/react-query";
import { assetsApi, projectsApi, runsApi, workspaceApi } from "@/api";

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
  journal: (projectId: string, experimentId: string, runId: string, executionId: string) =>
    [...runKeys.all, projectId, experimentId, runId, executionId, "journal"] as const,
  artifactContent: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    artifactId: string,
  ) =>
    [
      ...runKeys.all,
      projectId,
      experimentId,
      runId,
      executionId,
      "artifacts",
      artifactId,
      "content",
    ] as const,
  fileText: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    path: string,
  ) => [...runKeys.all, projectId, experimentId, runId, executionId, "files", path] as const,
  fileBlob: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    path: string,
  ) => [...runKeys.all, projectId, experimentId, runId, executionId, "blob", path] as const,
};

const ARTIFACT_PREVIEW_CAP = 300_000;

/** Poll the journal while an attempt is still active. A hidden tab does not poll. */
export const journalRefetchInterval = (status: string | undefined): number | false => {
  const folded = status?.toLowerCase();
  return folded === "running" || folded === "queued" || folded === "finalizing" ? 1500 : false;
};

/** Turn artifact bytes into preview text, capped at 300 000 characters. */
export const artifactPreviewText = (body: unknown): string => {
  const text = body == null ? "" : typeof body === "string" ? body : JSON.stringify(body, null, 2);
  return text.length > ARTIFACT_PREVIEW_CAP ? text.slice(0, ARTIFACT_PREVIEW_CAP) : text;
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

export const executionJournalQueryOptions = (
  projectId: string,
  experimentId: string,
  runId: string,
  executionId: string,
) =>
  queryOptions({
    queryKey: runKeys.journal(projectId, experimentId, runId, executionId),
    queryFn: async () => {
      const response = await runsApi.getRunExecution(projectId, experimentId, runId, executionId);
      return response.workflow ?? null;
    },
  });

export const artifactContentQueryOptions = (
  projectId: string,
  experimentId: string,
  runId: string,
  executionId: string,
  artifactId: string,
) =>
  queryOptions({
    queryKey: runKeys.artifactContent(projectId, experimentId, runId, executionId, artifactId),
    queryFn: async () =>
      artifactPreviewText(
        await runsApi.getArtifactContent(projectId, experimentId, runId, executionId, artifactId),
      ),
    staleTime: Number.POSITIVE_INFINITY,
  });

export const runFileTextQueryOptions = (
  projectId: string,
  experimentId: string,
  runId: string,
  executionId: string,
  path: string,
) =>
  queryOptions({
    queryKey: runKeys.fileText(projectId, experimentId, runId, executionId, path),
    queryFn: async () => {
      const response = await runsApi.getRunFileText(
        projectId,
        experimentId,
        runId,
        executionId,
        path,
      );
      return response.content;
    },
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

/**
 * Bytes of one file in an attempt, for previews text cannot show (images, PDF).
 *
 * The attempt directory comes from the server's file listing (`runDir`); the
 * client only appends the attempt-relative path the server already reported.
 */
export const runFileBlobQueryOptions = (
  projectId: string,
  experimentId: string,
  runId: string,
  executionId: string,
  path: string,
) =>
  queryOptions({
    queryKey: runKeys.fileBlob(projectId, experimentId, runId, executionId, path),
    queryFn: async (): Promise<Blob> => {
      const listing = await runsApi.getRunFiles(projectId, experimentId, runId, executionId);
      return workspaceApi.getWorkspaceFileBlob(`${listing.runDir.replace(/\/+$/, "")}/${path}`);
    },
    staleTime: Number.POSITIVE_INFINITY,
  });
