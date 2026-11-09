import { queryOptions } from "@tanstack/react-query";
import { assetsApi, projectsApi, runsApi, workspaceApi } from "@/api";
import { isActiveStatus } from "@/app/status/vocabulary";
import { getWorkspaceQueryScope } from "./workspaceSwitchEvents";

export const projectKeys = {
  all: ["projects"] as const,
  assets: (projectId: string) =>
    [...projectKeys.all, getWorkspaceQueryScope(), projectId, "assets"] as const,
};

export const assetKeys = {
  all: ["assets"] as const,
  detail: (projectId: string, assetId: string) =>
    [...assetKeys.all, getWorkspaceQueryScope(), projectId, assetId, "detail"] as const,
  text: (projectId: string, assetId: string, limit: number) =>
    [...assetKeys.all, getWorkspaceQueryScope(), projectId, assetId, "text", limit] as const,
};

export const runKeys = {
  all: ["runs"] as const,
  /** The workspace run inventory the project and experiment Overviews read. */
  inventory: () => [...runKeys.all, getWorkspaceQueryScope(), "inventory"] as const,
  metrics: (projectId: string, experimentId: string, runId: string, executionId: string) =>
    [
      ...runKeys.all,
      getWorkspaceQueryScope(),
      projectId,
      experimentId,
      runId,
      executionId,
      "metrics",
    ] as const,
  /** An attempt's file listing (the run views' files, L14). */
  files: (projectId: string, experimentId: string, runId: string, executionId: string) =>
    [
      ...runKeys.all,
      getWorkspaceQueryScope(),
      projectId,
      experimentId,
      runId,
      executionId,
      "files",
    ] as const,
  outputs: (projectId: string, experimentId: string, runId: string, executionId: string) =>
    [
      ...runKeys.all,
      getWorkspaceQueryScope(),
      projectId,
      experimentId,
      runId,
      executionId,
      "outputs",
    ] as const,
  /** One log stream of one attempt, accumulated window by window (`useExecutionLog`). */
  log: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    stream: "stdout" | "stderr" | "run",
  ) =>
    [
      ...runKeys.all,
      getWorkspaceQueryScope(),
      projectId,
      experimentId,
      runId,
      executionId,
      "log",
      stream,
    ] as const,
  journal: (projectId: string, experimentId: string, runId: string, executionId: string) =>
    [
      ...runKeys.all,
      getWorkspaceQueryScope(),
      projectId,
      experimentId,
      runId,
      executionId,
      "journal",
    ] as const,
  artifactContent: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    artifactId: string,
  ) =>
    [
      ...runKeys.all,
      getWorkspaceQueryScope(),
      projectId,
      experimentId,
      runId,
      executionId,
      "assets",
      artifactId,
      "content",
    ] as const,
  fileText: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    path: string,
  ) =>
    [
      ...runKeys.all,
      getWorkspaceQueryScope(),
      projectId,
      experimentId,
      runId,
      executionId,
      "files",
      path,
    ] as const,
  fileBlob: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    path: string,
  ) =>
    [
      ...runKeys.all,
      getWorkspaceQueryScope(),
      projectId,
      experimentId,
      runId,
      executionId,
      "blob",
      path,
    ] as const,
};

const ARTIFACT_PREVIEW_CAP = 300_000;

/** A structure is loaded whole. Cutting one mid-record makes the parser fail. */
export const STRUCTURE_PREVIEW_CAP = 8_000_000;

/** Poll the journal while an attempt is still active. A hidden tab does not poll. */
export const journalRefetchInterval = (status: string | undefined): number | false =>
  isActiveStatus(status) ? 1500 : false;

const artifactBodyText = (body: unknown): string =>
  body == null ? "" : typeof body === "string" ? body : JSON.stringify(body, null, 2);

/** Turn artifact bytes into preview text, capped at 300 000 characters. */
export const artifactPreviewText = (body: unknown): string => {
  const text = artifactBodyText(body);
  return text.length > ARTIFACT_PREVIEW_CAP ? text.slice(0, ARTIFACT_PREVIEW_CAP) : text;
};

/**
 * Structure files are not logs. A cap in the middle of a bond table is a
 * corrupt file, so this returns the whole text or refuses.
 */
export const structurePreviewText = (body: unknown): string => {
  const text = artifactBodyText(body);
  if (text.length > STRUCTURE_PREVIEW_CAP) {
    throw new Error(
      `Structure is ${text.length} characters, past the ${STRUCTURE_PREVIEW_CAP} preview limit.`,
    );
  }
  return text;
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

/** An asset's bytes as text, cut at `limit` (the asset preview, L08). Bytes never change. */
export const assetTextQueryOptions = (projectId: string, assetId: string, limit: number) =>
  queryOptions({
    queryKey: assetKeys.text(projectId, assetId, limit),
    queryFn: () => assetsApi.getText(projectId, assetId, limit),
    staleTime: Number.POSITIVE_INFINITY,
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
  complete = false,
) =>
  queryOptions({
    queryKey: complete
      ? ([
          ...runKeys.artifactContent(projectId, experimentId, runId, executionId, artifactId),
          "complete",
        ] as const)
      : runKeys.artifactContent(projectId, experimentId, runId, executionId, artifactId),
    queryFn: async () => {
      const body = await runsApi.getAssetContent(
        projectId,
        experimentId,
        runId,
        executionId,
        artifactId,
      );
      return complete ? structurePreviewText(body) : artifactPreviewText(body);
    },
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
/** An attempt's files (`runDir` + nodes), as the server lists them. */
export const runFilesQueryOptions = (
  projectId: string,
  experimentId: string,
  runId: string,
  executionId: string,
) =>
  queryOptions({
    queryKey: runKeys.files(projectId, experimentId, runId, executionId),
    queryFn: () => runsApi.getRunFiles(projectId, experimentId, runId, executionId),
    staleTime: 10_000,
  });

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

/** A workspace file's text (the Workflow view's Source of a code workflow, L06). */
export const fileKeys = {
  all: ["workspace-file"] as const,
  text: (path: string) => [...fileKeys.all, getWorkspaceQueryScope(), path, "text"] as const,
};

export const workspaceFileTextQueryOptions = (path: string) =>
  queryOptions({
    queryKey: fileKeys.text(path),
    queryFn: () => workspaceApi.getWorkspaceFileText(path),
    staleTime: 30_000,
  });

/** A workspace file's bytes (the image viewer, L07). */
export const workspaceFileBlobQueryOptions = (path: string) =>
  queryOptions({
    queryKey: [...fileKeys.all, getWorkspaceQueryScope(), path, "blob"] as const,
    queryFn: () => workspaceApi.getWorkspaceFileBlob(path),
    staleTime: 60_000,
  });
