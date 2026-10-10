import type { ArtifactPromoteRequest } from "@/api/generated/models/ArtifactPromoteRequest";
import type { ExecutionAttemptCreateRequest } from "@/api/generated/models/ExecutionAttemptCreateRequest";
import type { RunCreateRequest } from "@/api/generated/models/RunCreateRequest";
import type { RunFilesResponse } from "@/api/generated/models/RunFilesResponse";
import { RunsService } from "@/api/generated/services/RunsService";

export type { ArtifactResponse } from "@/api/generated/models/ArtifactResponse";
export type { ExecutionOutputsResponse } from "@/api/generated/models/ExecutionOutputsResponse";
export type { RunFilesResponse } from "@/api/generated/models/RunFilesResponse";
export type { RunFileTextResponse } from "@/api/generated/models/RunFileTextResponse";

export const runsApi = {
  listRuns: (projectId: string, experimentId: string) =>
    RunsService.listRuns(projectId, experimentId),
  createScopedRun: (projectId: string, experimentId: string, data: RunCreateRequest) =>
    RunsService.createScopedRun(projectId, experimentId, data),
  getRun: (projectId: string, experimentId: string, runId: string) =>
    RunsService.getRun(projectId, experimentId, runId),
  createExecution: (
    projectId: string,
    experimentId: string,
    runId: string,
    data: ExecutionAttemptCreateRequest,
  ) => RunsService.createExecution(projectId, experimentId, runId, data),
  getExecution: (projectId: string, experimentId: string, runId: string, executionId: string) =>
    RunsService.getExecutionRecord(projectId, experimentId, runId, executionId),
  getExecutionOutputs: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
  ) => RunsService.getExecutionOutputs(projectId, experimentId, runId, executionId),
  getArtifactContent: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    artifactId: string,
  ) => RunsService.downloadArtifactContent(projectId, experimentId, runId, executionId, artifactId),
  promoteArtifact: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    artifactId: string,
    data: ArtifactPromoteRequest,
  ) => RunsService.promoteArtifact(projectId, experimentId, runId, executionId, artifactId, data),
  getRunExecutionLogs: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
  ) => RunsService.getRunExecutionLogs(projectId, experimentId, runId, executionId),
  getRunExecution: (projectId: string, experimentId: string, runId: string, executionId: string) =>
    RunsService.getRunExecution(projectId, experimentId, runId, executionId),
  getRunFileText: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    path: string,
  ) => RunsService.getRunFileText(projectId, experimentId, runId, executionId, path),
  getRunFiles: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
  ): Promise<RunFilesResponse> =>
    RunsService.getRunFiles(projectId, experimentId, runId, executionId),
  /**
   * The same reads, addressed at an explicit served workspace.
   *
   * `/api/workspaces/{ws}/…` is a full mirror of the run routes, gated on a
   * valid `{ws}` — so a comparison spanning workspaces reads every run through
   * the same surface, with the workspace named rather than implied by whichever
   * one happens to be active.
   */
  getRunFilesWs: (
    ws: string,
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
  ): Promise<RunFilesResponse> =>
    RunsService.getRunFilesWs(projectId, experimentId, runId, executionId, ws),
  getRunFileTextWs: (
    ws: string,
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    path: string,
  ) => RunsService.getRunFileTextWs(projectId, experimentId, runId, executionId, ws, path),
  listExecutions: (projectId: string, experimentId: string, runId: string) =>
    RunsService.listExecutions(projectId, experimentId, runId),
  listExecutionsWs: (ws: string, projectId: string, experimentId: string, runId: string) =>
    RunsService.listExecutionsWs(projectId, experimentId, runId, ws),
  cancelExecution: (projectId: string, experimentId: string, runId: string, executionId: string) =>
    RunsService.cancelExecution(projectId, experimentId, runId, executionId),
  exportUrl: (projectId: string, experimentId: string, runId: string): string =>
    `/api/projects/${encodeURIComponent(projectId)}/experiments/${encodeURIComponent(experimentId)}/runs/${encodeURIComponent(runId)}/export`,
};
