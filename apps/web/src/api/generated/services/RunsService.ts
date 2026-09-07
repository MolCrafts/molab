/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ArtifactPromoteRequest } from '../models/ArtifactPromoteRequest';
import type { ArtifactPromotionResponse } from '../models/ArtifactPromotionResponse';
import type { ExecutionAttemptCreateRequest } from '../models/ExecutionAttemptCreateRequest';
import type { ExecutionCreateRequest } from '../models/ExecutionCreateRequest';
import type { ExecutionOutputsResponse } from '../models/ExecutionOutputsResponse';
import type { ExecutionResponse } from '../models/ExecutionResponse';
import type { RunAnalyzeFailureRequest } from '../models/RunAnalyzeFailureRequest';
import type { RunCreateRequest } from '../models/RunCreateRequest';
import type { RunExecutionResponse } from '../models/RunExecutionResponse';
import type { RunFilesResponse } from '../models/RunFilesResponse';
import type { RunFileTextResponse } from '../models/RunFileTextResponse';
import type { RunHarvestRequest } from '../models/RunHarvestRequest';
import type { RunLogsResponse } from '../models/RunLogsResponse';
import type { RunResponse } from '../models/RunResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class RunsService {
    /**
     * List Runs
     * @param projectId
     * @param experimentId
     * @param molexpSession
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static listRuns(
        projectId: string,
        experimentId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<Array<RunResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Scoped Run
     * @param projectId
     * @param experimentId
     * @param requestBody
     * @param molexpSession
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static createScopedRun(
        projectId: string,
        experimentId: string,
        requestBody: RunCreateRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<RunResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run
     * @param projectId
     * @param experimentId
     * @param runId
     * @param molexpSession
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static getRun(
        projectId: string,
        experimentId: string,
        runId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Execution
     * Create one queued physical attempt without mutating the Run.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param requestBody
     * @param molexpSession
     * @returns ExecutionResponse Successful Response
     * @throws ApiError
     */
    public static createExecution(
        projectId: string,
        experimentId: string,
        runId: string,
        requestBody: ExecutionAttemptCreateRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<ExecutionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Executions
     * Every attempt at this Run, oldest first (``e01``, ``e02``, …).
     *
     * The Run detail already embeds these; this is the addressable list for a
     * caller that wants the attempts alone, and the GET counterpart of the POST
     * on the same path.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param molexpSession
     * @returns ExecutionResponse Successful Response
     * @throws ApiError
     */
    public static listExecutions(
        projectId: string,
        experimentId: string,
        runId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<Array<ExecutionResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Execution Record
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param molexpSession
     * @returns ExecutionResponse Successful Response
     * @throws ApiError
     */
    public static getExecutionRecord(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<ExecutionResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Execution Outputs
     * Separate stdio, managed Artifacts, evidence, and unregistered work files.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param molexpSession
     * @returns ExecutionOutputsResponse Successful Response
     * @throws ApiError
     */
    public static getExecutionOutputs(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<ExecutionOutputsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/outputs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Promote Artifact
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param artifactId
     * @param requestBody
     * @param molexpSession
     * @returns ArtifactPromotionResponse Successful Response
     * @throws ApiError
     */
    public static promoteArtifact(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        artifactId: string,
        requestBody: ArtifactPromoteRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<ArtifactPromotionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/artifacts/{artifact_id}/promote',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
                'artifact_id': artifactId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Download Artifact Content
     * Stream one Execution Artifact's bytes from the authoritative manifest.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param artifactId
     * @param molexpSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadArtifactContent(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        artifactId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/artifacts/{artifact_id}/content',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
                'artifact_id': artifactId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run Execution Logs
     * Return stdout/stderr for a specific execution attempt.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param molexpSession
     * @returns RunLogsResponse Successful Response
     * @throws ApiError
     */
    public static getRunExecutionLogs(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunLogsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/logs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run File Text
     * Return the raw text content of a file under the run directory.
     *
     * Routes through ``workspace.fs`` — same path as workspace file reads —
     * so remote workspaces resolve correctly.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param path Relative path under the Execution directory
     * @param molexpSession
     * @returns RunFileTextResponse Successful Response
     * @throws ApiError
     */
    public static getRunFileText(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        path: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunFileTextResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/file/text',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            query: {
                'path': path,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run Execution
     * Return runtime workflow graph state from workflow.json.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param molexpSession
     * @returns RunExecutionResponse Successful Response
     * @throws ApiError
     */
    public static getRunExecution(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunExecutionResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/workflow',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run Files
     * Return the on-disk file tree for a run, enriched with catalog metadata.
     *
     * Uses the **same** :func:`~molexp.workspace.fs_tree.list_tree_children` walk
     * as workspace file listing (via ``workspace.fs``) so remote workspaces
     * activate plugins the same way as local ones. Catalog enrichment is
     * best-effort for local asset scans only.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param molexpSession
     * @returns RunFilesResponse Successful Response
     * @throws ApiError
     */
    public static getRunFiles(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunFilesResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/files',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Cancel Execution
     * Cancel one explicit Execution; Run has no cancellable scalar state.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param molexpSession
     * @returns ExecutionResponse Successful Response
     * @throws ApiError
     */
    public static cancelExecution(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<ExecutionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/cancel',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Export Run
     * Stream a zip archive of the run directory (artifacts, logs, metadata).
     * @param projectId
     * @param experimentId
     * @param runId
     * @param molexpSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static exportRun(
        projectId: string,
        experimentId: string,
        runId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/export',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Harvest Run Route
     * Harvest a terminal run into a sourced KnowledgeItem under its experiment.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param requestBody
     * @param molexpSession
     * @returns string Successful Response
     * @throws ApiError
     */
    public static harvestRunRoute(
        projectId: string,
        experimentId: string,
        runId: string,
        requestBody: RunHarvestRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/harvest',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Ingest Run Metrics
     * Ingest foreign logs into the run host metrics surface (additive).
     *
     * Shares :func:`molexp.plugins.metrics_ingest.ingest_run` with the CLI.
     * Skips are returned; the route does not fail the whole call when one
     * converter cannot run.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param molexpSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static ingestRunMetrics(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/molplot/ingest',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Analyze Run Failure Route
     * Analyze a failed run into a sourced FailureAnalysis KnowledgeItem.
     *
     * Shares :func:`molexp.services.run_failure.analyze_run_failure` with the CLI
     * (close-loop-02). Deterministic narrative when ``narrative`` is omitted.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param requestBody
     * @param molexpSession
     * @returns string Successful Response
     * @throws ApiError
     */
    public static analyzeRunFailureRoute(
        projectId: string,
        experimentId: string,
        runId: string,
        requestBody: RunAnalyzeFailureRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/analyze-failure',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Run
     * Create a run in a specific project/experiment (body carries scope ids).
     *
     * If ``request.workflow_json`` is supplied and the experiment has no
     * workflow bound, compile and persist the IR before the run is
     * materialized so worker processes can pick it up off disk.
     * @param requestBody
     * @param molexpSession
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static createRun(
        requestBody: ExecutionCreateRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<RunResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/runs',
            cookies: {
                'molexp_session': molexpSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Runs
     * @param projectId
     * @param experimentId
     * @param ws
     * @param molexpSession
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static listRunsWs(
        projectId: string,
        experimentId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<Array<RunResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Scoped Run
     * @param projectId
     * @param experimentId
     * @param ws
     * @param requestBody
     * @param molexpSession
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static createScopedRunWs(
        projectId: string,
        experimentId: string,
        ws: string,
        requestBody: RunCreateRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<RunResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param molexpSession
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static getRunWs(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Execution
     * Create one queued physical attempt without mutating the Run.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param requestBody
     * @param molexpSession
     * @returns ExecutionResponse Successful Response
     * @throws ApiError
     */
    public static createExecutionWs(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        requestBody: ExecutionAttemptCreateRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<ExecutionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Executions
     * Every attempt at this Run, oldest first (``e01``, ``e02``, …).
     *
     * The Run detail already embeds these; this is the addressable list for a
     * caller that wants the attempts alone, and the GET counterpart of the POST
     * on the same path.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param molexpSession
     * @returns ExecutionResponse Successful Response
     * @throws ApiError
     */
    public static listExecutionsWs(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<Array<ExecutionResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Execution Record
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param ws
     * @param molexpSession
     * @returns ExecutionResponse Successful Response
     * @throws ApiError
     */
    public static getExecutionRecordWs(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<ExecutionResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Execution Outputs
     * Separate stdio, managed Artifacts, evidence, and unregistered work files.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param ws
     * @param molexpSession
     * @returns ExecutionOutputsResponse Successful Response
     * @throws ApiError
     */
    public static getExecutionOutputsWs(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<ExecutionOutputsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/outputs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Promote Artifact
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param artifactId
     * @param ws
     * @param requestBody
     * @param molexpSession
     * @returns ArtifactPromotionResponse Successful Response
     * @throws ApiError
     */
    public static promoteArtifactWs(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        artifactId: string,
        ws: string,
        requestBody: ArtifactPromoteRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<ArtifactPromotionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/artifacts/{artifact_id}/promote',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
                'artifact_id': artifactId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Download Artifact Content
     * Stream one Execution Artifact's bytes from the authoritative manifest.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param artifactId
     * @param ws
     * @param molexpSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadArtifactContentWs(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        artifactId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/artifacts/{artifact_id}/content',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
                'artifact_id': artifactId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run Execution Logs
     * Return stdout/stderr for a specific execution attempt.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param ws
     * @param molexpSession
     * @returns RunLogsResponse Successful Response
     * @throws ApiError
     */
    public static getRunExecutionLogsWs(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunLogsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/logs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run File Text
     * Return the raw text content of a file under the run directory.
     *
     * Routes through ``workspace.fs`` — same path as workspace file reads —
     * so remote workspaces resolve correctly.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param ws
     * @param path Relative path under the Execution directory
     * @param molexpSession
     * @returns RunFileTextResponse Successful Response
     * @throws ApiError
     */
    public static getRunFileTextWs(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        ws: string,
        path: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunFileTextResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/file/text',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            query: {
                'path': path,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run Execution
     * Return runtime workflow graph state from workflow.json.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param ws
     * @param molexpSession
     * @returns RunExecutionResponse Successful Response
     * @throws ApiError
     */
    public static getRunExecutionWs(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunExecutionResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/workflow',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run Files
     * Return the on-disk file tree for a run, enriched with catalog metadata.
     *
     * Uses the **same** :func:`~molexp.workspace.fs_tree.list_tree_children` walk
     * as workspace file listing (via ``workspace.fs``) so remote workspaces
     * activate plugins the same way as local ones. Catalog enrichment is
     * best-effort for local asset scans only.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param ws
     * @param molexpSession
     * @returns RunFilesResponse Successful Response
     * @throws ApiError
     */
    public static getRunFilesWs(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunFilesResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/files',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Cancel Execution
     * Cancel one explicit Execution; Run has no cancellable scalar state.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param ws
     * @param molexpSession
     * @returns ExecutionResponse Successful Response
     * @throws ApiError
     */
    public static cancelExecutionWs(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<ExecutionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/cancel',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Export Run
     * Stream a zip archive of the run directory (artifacts, logs, metadata).
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param molexpSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static exportRunWs(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/export',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Harvest Run Route
     * Harvest a terminal run into a sourced KnowledgeItem under its experiment.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param requestBody
     * @param molexpSession
     * @returns string Successful Response
     * @throws ApiError
     */
    public static harvestRunRouteWs(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        requestBody: RunHarvestRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/harvest',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Ingest Run Metrics
     * Ingest foreign logs into the run host metrics surface (additive).
     *
     * Shares :func:`molexp.plugins.metrics_ingest.ingest_run` with the CLI.
     * Skips are returned; the route does not fail the whole call when one
     * converter cannot run.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param ws
     * @param molexpSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static ingestRunMetricsWs(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions/{execution_id}/molplot/ingest',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'execution_id': executionId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Analyze Run Failure Route
     * Analyze a failed run into a sourced FailureAnalysis KnowledgeItem.
     *
     * Shares :func:`molexp.services.run_failure.analyze_run_failure` with the CLI
     * (close-loop-02). Deterministic narrative when ``narrative`` is omitted.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param requestBody
     * @param molexpSession
     * @returns string Successful Response
     * @throws ApiError
     */
    public static analyzeRunFailureRouteWs(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        requestBody: RunAnalyzeFailureRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/analyze-failure',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Run
     * Create a run in a specific project/experiment (body carries scope ids).
     *
     * If ``request.workflow_json`` is supplied and the experiment has no
     * workflow bound, compile and persist the IR before the run is
     * materialized so worker processes can pick it up off disk.
     * @param ws
     * @param requestBody
     * @param molexpSession
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static createRunWs(
        ws: string,
        requestBody: ExecutionCreateRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<RunResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/runs',
            path: {
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
