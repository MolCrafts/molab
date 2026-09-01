import type { RunCreateRequest } from "@/api/generated/models/RunCreateRequest";
import type { RunFilesResponse } from "@/api/generated/models/RunFilesResponse";
import type { RunMetricsResponse as GeneratedRunMetricsResponse } from "@/api/generated/models/RunMetricsResponse";
import { RunsService } from "@/api/generated/services/RunsService";

export type { LammpsLogResponse } from "@/api/generated/models/LammpsLogResponse";
export type { LammpsThermoStage } from "@/api/generated/models/LammpsThermoStage";
export type { RunActionResponse } from "@/api/generated/models/RunActionResponse";
export type { RunContinueResponse } from "@/api/generated/models/RunContinueResponse";
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
  getRunLogs: (projectId: string, experimentId: string, runId: string) =>
    RunsService.getRunLogs(projectId, experimentId, runId),
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
    executionId?: string | null,
  ) => RunsService.getRunExecution(projectId, experimentId, runId, executionId),
  getRunLammpsLog: (projectId: string, experimentId: string, runId: string, path: string) =>
    RunsService.getRunLammpsLog(projectId, experimentId, runId, path),
  getRunFileText: (projectId: string, experimentId: string, runId: string, path: string) =>
    RunsService.getRunFileText(projectId, experimentId, runId, path),
  getRunMetrics: async (
    projectId: string,
    experimentId: string,
    runId: string,
    query: RunMetricsQuery = {},
  ): Promise<RunMetricsResponse> => {
    const raw = await RunsService.getRunMetrics(
      projectId,
      experimentId,
      runId,
      query.type,
      query.key,
      query.sinceLine,
      query.limit,
    );
    return mapMetrics(raw);
  },
  updateRunStatus: async (
    projectId: string,
    experimentId: string,
    runId: string,
    status: string,
  ): Promise<void> => {
    await RunsService.updateRunStatus(projectId, experimentId, runId, { status });
  },
  getRunFiles: (
    projectId: string,
    experimentId: string,
    runId: string,
  ): Promise<RunFilesResponse> => RunsService.getRunFiles(projectId, experimentId, runId),
  cancelRun: (projectId: string, experimentId: string, runId: string) =>
    RunsService.cancelRun(projectId, experimentId, runId),
  resumeRun: (projectId: string, experimentId: string, runId: string) =>
    RunsService.resumeRun(projectId, experimentId, runId),
  rerunRun: (projectId: string, experimentId: string, runId: string, fresh = false) =>
    RunsService.rerunRun(projectId, experimentId, runId, fresh),
  startRun: (
    projectId: string,
    experimentId: string,
    runId: string,
    target: string,
    params?: Record<string, unknown>,
  ) =>
    RunsService.startRun(projectId, experimentId, runId, {
      target,
      params: params ?? null,
    }),
  exportUrl: (projectId: string, experimentId: string, runId: string): string =>
    `/api/projects/${encodeURIComponent(projectId)}/experiments/${encodeURIComponent(experimentId)}/runs/${encodeURIComponent(runId)}/export`,
};
