import type { ArtifactPromoteRequest } from "@/api/generated/models/ArtifactPromoteRequest";
import type { ExecutionAttemptCreateRequest } from "@/api/generated/models/ExecutionAttemptCreateRequest";
import type { RunCreateRequest } from "@/api/generated/models/RunCreateRequest";
import type { RunFilesResponse } from "@/api/generated/models/RunFilesResponse";
import type { RunMetricsResponse as GeneratedRunMetricsResponse } from "@/api/generated/models/RunMetricsResponse";
import { RunsService } from "@/api/generated/services/RunsService";

export type { ArtifactResponse } from "@/api/generated/models/ArtifactResponse";
export type { ExecutionOutputsResponse } from "@/api/generated/models/ExecutionOutputsResponse";
export type { ExecutionRecordResponse } from "@/api/generated/models/ExecutionRecordResponse";
export type { LammpsLogResponse } from "@/api/generated/models/LammpsLogResponse";
export type { LammpsThermoStage } from "@/api/generated/models/LammpsThermoStage";
export type { RunFilesResponse } from "@/api/generated/models/RunFilesResponse";
export type { RunFileTextResponse } from "@/api/generated/models/RunFileTextResponse";

export interface MetricRecord {
  t: string;
  k: string;
  s?: number;
  w?: string;
  v?: unknown;
  tags?: Record<string, unknown>;
}

export interface MetricSeriesSummary {
  key: string;
  type: string;
  count: number;
  latestStep?: number | null;
  latestTimestamp?: string | null;
  latestValue?: unknown;
}

export interface RunMetricsResponse {
  nextLine: number;
  records: MetricRecord[];
  series: MetricSeriesSummary[];
  parseErrors: number;
}

export interface RunMetricsQuery {
  type?: string;
  key?: string;
  sinceLine?: number;
  limit?: number;
}

const mapMetrics = (raw: GeneratedRunMetricsResponse): RunMetricsResponse => ({
  nextLine: raw.nextLine ?? 0,
  records: (raw.records ?? []) as MetricRecord[],
  series: (raw.series ?? []).map((row) => ({
    key: row.key,
    type: row.type,
    count: row.count,
    latestStep: row.latestStep,
    latestTimestamp: row.latestTimestamp,
    latestValue: row.latestValue,
  })),
  parseErrors: raw.parseErrors ?? 0,
});

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
  promoteArtifact: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    artifactId: string,
    data: ArtifactPromoteRequest,
  ) =>
    RunsService.promoteArtifact(
      projectId,
      experimentId,
      runId,
      executionId,
      artifactId,
      data,
    ),
  getRunExecutionLogs: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
  ) => RunsService.getRunExecutionLogs(projectId, experimentId, runId, executionId),
  getRunExecution: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
  ) => RunsService.getRunExecution(projectId, experimentId, runId, executionId),
  getRunLammpsLog: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    path: string,
  ) => RunsService.getRunLammpsLog(projectId, experimentId, runId, executionId, path),
  getRunFileText: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    path: string,
  ) => RunsService.getRunFileText(projectId, experimentId, runId, executionId, path),
  getRunMetrics: async (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
    query: RunMetricsQuery = {},
  ): Promise<RunMetricsResponse> => {
    const raw = await RunsService.getRunMetrics(
      projectId,
      experimentId,
      runId,
      executionId,
      query.type,
      query.key,
      query.sinceLine,
      query.limit,
    );
    return mapMetrics(raw);
  },
  getRunFiles: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
  ): Promise<RunFilesResponse> =>
    RunsService.getRunFiles(projectId, experimentId, runId, executionId),
  cancelExecution: (
    projectId: string,
    experimentId: string,
    runId: string,
    executionId: string,
  ) => RunsService.cancelExecution(projectId, experimentId, runId, executionId),
  exportUrl: (projectId: string, experimentId: string, runId: string): string =>
    `/api/projects/${encodeURIComponent(projectId)}/experiments/${encodeURIComponent(experimentId)}/runs/${encodeURIComponent(runId)}/export`,
};
