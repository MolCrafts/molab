/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ExecutionCreateRequest } from '../models/ExecutionCreateRequest';
import type { LammpsLogResponse } from '../models/LammpsLogResponse';
import type { RunActionResponse } from '../models/RunActionResponse';
import type { RunAnalyzeFailureRequest } from '../models/RunAnalyzeFailureRequest';
import type { RunContinueResponse } from '../models/RunContinueResponse';
import type { RunCreateRequest } from '../models/RunCreateRequest';
import type { RunExecutionResponse } from '../models/RunExecutionResponse';
import type { RunFilesResponse } from '../models/RunFilesResponse';
import type { RunFileTextResponse } from '../models/RunFileTextResponse';
import type { RunHarvestRequest } from '../models/RunHarvestRequest';
import type { RunLogsResponse } from '../models/RunLogsResponse';
import type { RunMetricsResponse } from '../models/RunMetricsResponse';
import type { RunResponse } from '../models/RunResponse';
import type { RunStartRequest } from '../models/RunStartRequest';
import type { RunStatusResponse } from '../models/RunStatusResponse';
import type { RunStatusUpdateRequest } from '../models/RunStatusUpdateRequest';
import type { WorkspaceEventResponse } from '../models/WorkspaceEventResponse';
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
     * Create Run
     * @param projectId
     * @param experimentId
     * @param requestBody
     * @param molexpSession
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static createRun(
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
     * Cancel Run
     * Cancel a run.
     *
     * ``cancel`` is the canonical verb (matching the CLI ``molexp runs cancel``
     * and the resulting ``cancelled`` status); ``/kill`` remains as a
     * deprecated alias route bound to this same handler.
     *
     * One shared body with the CLI and the harness capability:
     * :func:`molexp.workspace.lifecycle_ops.cancel_run` (reap → domain check →
     * signal → flip), with :func:`molexp.plugins.submit_molq.cancel.try_cancel`
     * injected as the executor-signal hook (molq :class:`molq.Submitor` for
     * cluster-submitted runs, ``SIGTERM`` for a local pid). A run outside the
     * cancellable domain (pending / succeeded / already stopped) is a 409 with
     * the verb that owns it — never a silent status flip.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param molexpSession
     * @returns RunActionResponse Successful Response
     * @throws ApiError
     */
    public static cancelRun(
        projectId: string,
        experimentId: string,
        runId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunActionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/cancel',
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
     * Get Run Events
     * Return the run's recent workspace-timeline events, newest first.
     *
     * Reads the default-on ``workspace.events.sqlite`` spine via the shared
     * :func:`molexp.workspace.events.read_workspace_events` (the same code path
     * ``molexp runs info`` uses). A workspace with no timeline yet (nothing has
     * emitted) returns ``[]``.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param limit
     * @param molexpSession
     * @returns WorkspaceEventResponse Successful Response
     * @throws ApiError
     */
    public static getRunEvents(
        projectId: string,
        experimentId: string,
        runId: string,
        limit: number = 50,
        molexpSession?: (string | null),
    ): CancelablePromise<Array<WorkspaceEventResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/events',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            query: {
                'limit': limit,
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
     * @param executionId Execution attempt id.
     * @param molexpSession
     * @returns RunExecutionResponse Successful Response
     * @throws ApiError
     */
    public static getRunExecution(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId?: (string | null),
        molexpSession?: (string | null),
    ): CancelablePromise<RunExecutionResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/execution',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            query: {
                'execution_id': executionId,
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
     * Get Run File Text
     * Return the raw text content of a file under the run directory.
     *
     * Routes through ``workspace._fs`` — same path as workspace file reads —
     * so remote workspaces resolve correctly.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param path Relative path under run_dir
     * @param molexpSession
     * @returns RunFileTextResponse Successful Response
     * @throws ApiError
     */
    public static getRunFileText(
        projectId: string,
        experimentId: string,
        runId: string,
        path: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunFileTextResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/file/text',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * Get Run Files
     * Return the on-disk file tree for a run, enriched with catalog metadata.
     *
     * Uses the **same** :func:`~molexp.workspace.fs_tree.list_tree_children` walk
     * as workspace file listing (via ``workspace._fs``) so remote workspaces
     * activate plugins the same way as local ones. Catalog enrichment is
     * best-effort for local asset scans only.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param molexpSession
     * @returns RunFilesResponse Successful Response
     * @throws ApiError
     */
    public static getRunFiles(
        projectId: string,
        experimentId: string,
        runId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunFilesResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/files',
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
     * @deprecated
     * Cancel Run
     * Deprecated alias for `POST .../{run_id}/cancel` (same handler).
     * @param projectId
     * @param experimentId
     * @param runId
     * @param molexpSession
     * @returns RunActionResponse Successful Response
     * @throws ApiError
     */
    public static cancelRun1(
        projectId: string,
        experimentId: string,
        runId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunActionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/kill',
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
     * Get Run Lammps Log
     * Parse a LAMMPS log file and return thermo stages.
     *
     * Inlined parser — ``molpy.io`` does not export a multi-stage log
     * reader, so the route owns this lightweight regex-based parse to
     * avoid coupling the API surface to a transient molpy refactor.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param path Relative path of the log file under run_dir
     * @param molexpSession
     * @returns LammpsLogResponse Successful Response
     * @throws ApiError
     */
    public static getRunLammpsLog(
        projectId: string,
        experimentId: string,
        runId: string,
        path: string,
        molexpSession?: (string | null),
    ): CancelablePromise<LammpsLogResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/lammps-log',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * Get Run Logs
     * Return stdout/stderr for the most recent execution of a run.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param molexpSession
     * @returns RunLogsResponse Successful Response
     * @throws ApiError
     */
    public static getRunLogs(
        projectId: string,
        experimentId: string,
        runId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunLogsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/logs',
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
     * Get Run Metrics
     * Return run-local metrics (dense Zarr SoT, else JSONL WAL).
     * @param projectId
     * @param experimentId
     * @param runId
     * @param type
     * @param key
     * @param sinceLine
     * @param limit
     * @param molexpSession
     * @returns RunMetricsResponse Successful Response
     * @throws ApiError
     */
    public static getRunMetrics(
        projectId: string,
        experimentId: string,
        runId: string,
        type?: (string | null),
        key?: (string | null),
        sinceLine?: number,
        limit: number = 5000,
        molexpSession?: (string | null),
    ): CancelablePromise<RunMetricsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/metrics',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            query: {
                'type': type,
                'key': key,
                'since_line': sinceLine,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Detect Run Metrics Sources
     * Classify foreign log formats under the run directory (read-only).
     *
     * Does not write the metrics buffer. Host ≠ MolRec: detection never invents
     * meta/status sections.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param molexpSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static detectRunMetricsSources(
        projectId: string,
        experimentId: string,
        runId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/metrics/detect',
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
     * Ingest Run Metrics
     * Ingest foreign logs into the run host metrics surface (additive).
     *
     * Shares :func:`molexp.plugins.metrics_ingest.ingest_run` with the CLI.
     * Skips are returned; the route does not fail the whole call when one
     * converter cannot run.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param molexpSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static ingestRunMetrics(
        projectId: string,
        experimentId: string,
        runId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/metrics/ingest',
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
     * Rerun Run
     * Rerun a failed/cancelled run in a new execution (no clone).
     *
     * A fresh ``exec-{run_id}-N`` is derived and, for a targeted run, dispatched
     * through molq; no parameters are cloned and no new Run is created. Note the
     * content-addressed cache may still serve deterministic tasks — pass
     * ``fresh=true`` to bypass cache reads (persisted as a marker in the new
     * execution slot, so whichever process executes it honors the request).
     * 409 unless the run is failed/cancelled (pending/succeeded/running are not
     * rerun's job). A stale ``running`` run with a dead owner is reaped to
     * ``failed`` first (run-recovery bug 5).
     * @param projectId
     * @param experimentId
     * @param runId
     * @param fresh Bypass content-addressed cache reads for the new execution: every task body actually re-runs (results are still written back to the cache). Same capability as the CLI's `molexp run --rerun --fresh`.
     * @param molexpSession
     * @returns RunContinueResponse Successful Response
     * @throws ApiError
     */
    public static rerunRun(
        projectId: string,
        experimentId: string,
        runId: string,
        fresh: boolean = false,
        molexpSession?: (string | null),
    ): CancelablePromise<RunContinueResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/rerun',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            query: {
                'fresh': fresh,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Resume Run
     * Resume a failed/cancelled run: reopen its last non-succeeded execution.
     *
     * The reopened execution is re-dispatched on the same ``execution_id``; the
     * worker seeds already-completed nodes from disk and recomputes the rest.
     * 409 unless the run is failed/cancelled (pending/succeeded/running are not
     * resume's job). A stale ``running`` run with a dead owner is reaped to
     * ``failed`` first, so it enters the retryable domain instead of 409-ing
     * forever (run-recovery bug 5).
     * @param projectId
     * @param experimentId
     * @param runId
     * @param molexpSession
     * @returns RunContinueResponse Successful Response
     * @throws ApiError
     */
    public static resumeRun(
        projectId: string,
        experimentId: string,
        runId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunContinueResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/resume',
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
     * Start Run
     * Start a pending run by dispatching it to a compute target (the ``run`` verb).
     *
     * The disjoint counterpart to resume/rerun: ``run`` owns ``pending`` runs only
     * (409 otherwise — retrying a failed/cancelled run is resume/rerun's job, and a
     * live ``running`` run must not get a second execution). A pending run is
     * target-less (the create+dispatch contract dispatches a targeted run on
     * create), so Start supplies the target to execute on; a target-less Start
     * (no body target, none recorded) 422s — those run via ``molexp run`` on the
     * host, since the server never executes a workflow in-process.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param requestBody
     * @param molexpSession
     * @returns RunContinueResponse Successful Response
     * @throws ApiError
     */
    public static startRun(
        projectId: string,
        experimentId: string,
        runId: string,
        requestBody: RunStartRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<RunContinueResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/run',
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
     * Update Run Status
     * Mark a run ``cancelled`` — the one status a client may write directly.
     *
     * Every other status is owned by the run lifecycle (the three-verb law):
     * ``running``/``succeeded``/``failed`` are stamped by the executing
     * process, never by a client, and retrying goes through the explicit
     * ``resume``/``rerun`` routes. Requests for any status but ``cancelled``
     * are refused with 409; prefer ``POST .../{run_id}/cancel`` (which also
     * signals the live executor) over this raw mark.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param requestBody
     * @param molexpSession
     * @returns RunStatusResponse Successful Response
     * @throws ApiError
     */
    public static updateRunStatus(
        projectId: string,
        experimentId: string,
        runId: string,
        requestBody: RunStatusUpdateRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<RunStatusResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/status',
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
    public static createRun1(
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
    public static listRuns1(
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
     * Create Run
     * @param projectId
     * @param experimentId
     * @param ws
     * @param requestBody
     * @param molexpSession
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static createRun2(
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
    public static getRun1(
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
    public static analyzeRunFailureRoute1(
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
     * Cancel Run
     * Cancel a run.
     *
     * ``cancel`` is the canonical verb (matching the CLI ``molexp runs cancel``
     * and the resulting ``cancelled`` status); ``/kill`` remains as a
     * deprecated alias route bound to this same handler.
     *
     * One shared body with the CLI and the harness capability:
     * :func:`molexp.workspace.lifecycle_ops.cancel_run` (reap → domain check →
     * signal → flip), with :func:`molexp.plugins.submit_molq.cancel.try_cancel`
     * injected as the executor-signal hook (molq :class:`molq.Submitor` for
     * cluster-submitted runs, ``SIGTERM`` for a local pid). A run outside the
     * cancellable domain (pending / succeeded / already stopped) is a 409 with
     * the verb that owns it — never a silent status flip.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param molexpSession
     * @returns RunActionResponse Successful Response
     * @throws ApiError
     */
    public static cancelRun2(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunActionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/cancel',
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
     * Get Run Events
     * Return the run's recent workspace-timeline events, newest first.
     *
     * Reads the default-on ``workspace.events.sqlite`` spine via the shared
     * :func:`molexp.workspace.events.read_workspace_events` (the same code path
     * ``molexp runs info`` uses). A workspace with no timeline yet (nothing has
     * emitted) returns ``[]``.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param limit
     * @param molexpSession
     * @returns WorkspaceEventResponse Successful Response
     * @throws ApiError
     */
    public static getRunEvents1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        limit: number = 50,
        molexpSession?: (string | null),
    ): CancelablePromise<Array<WorkspaceEventResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/events',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            query: {
                'limit': limit,
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
     * @param ws
     * @param executionId Execution attempt id.
     * @param molexpSession
     * @returns RunExecutionResponse Successful Response
     * @throws ApiError
     */
    public static getRunExecution1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        executionId?: (string | null),
        molexpSession?: (string | null),
    ): CancelablePromise<RunExecutionResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/execution',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            query: {
                'execution_id': executionId,
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
    public static getRunExecutionLogs1(
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
    public static exportRun1(
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
     * Get Run File Text
     * Return the raw text content of a file under the run directory.
     *
     * Routes through ``workspace._fs`` — same path as workspace file reads —
     * so remote workspaces resolve correctly.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param path Relative path under run_dir
     * @param molexpSession
     * @returns RunFileTextResponse Successful Response
     * @throws ApiError
     */
    public static getRunFileText1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        path: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunFileTextResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/file/text',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * Get Run Files
     * Return the on-disk file tree for a run, enriched with catalog metadata.
     *
     * Uses the **same** :func:`~molexp.workspace.fs_tree.list_tree_children` walk
     * as workspace file listing (via ``workspace._fs``) so remote workspaces
     * activate plugins the same way as local ones. Catalog enrichment is
     * best-effort for local asset scans only.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param molexpSession
     * @returns RunFilesResponse Successful Response
     * @throws ApiError
     */
    public static getRunFiles1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunFilesResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/files',
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
    public static harvestRunRoute1(
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
     * @deprecated
     * Cancel Run
     * Deprecated alias for `POST .../{run_id}/cancel` (same handler).
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param molexpSession
     * @returns RunActionResponse Successful Response
     * @throws ApiError
     */
    public static cancelRun3(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunActionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/kill',
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
     * Get Run Lammps Log
     * Parse a LAMMPS log file and return thermo stages.
     *
     * Inlined parser — ``molpy.io`` does not export a multi-stage log
     * reader, so the route owns this lightweight regex-based parse to
     * avoid coupling the API surface to a transient molpy refactor.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param path Relative path of the log file under run_dir
     * @param molexpSession
     * @returns LammpsLogResponse Successful Response
     * @throws ApiError
     */
    public static getRunLammpsLog1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        path: string,
        molexpSession?: (string | null),
    ): CancelablePromise<LammpsLogResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/lammps-log',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * Get Run Logs
     * Return stdout/stderr for the most recent execution of a run.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param molexpSession
     * @returns RunLogsResponse Successful Response
     * @throws ApiError
     */
    public static getRunLogs1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunLogsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/logs',
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
     * Get Run Metrics
     * Return run-local metrics (dense Zarr SoT, else JSONL WAL).
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param type
     * @param key
     * @param sinceLine
     * @param limit
     * @param molexpSession
     * @returns RunMetricsResponse Successful Response
     * @throws ApiError
     */
    public static getRunMetrics1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        type?: (string | null),
        key?: (string | null),
        sinceLine?: number,
        limit: number = 5000,
        molexpSession?: (string | null),
    ): CancelablePromise<RunMetricsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/metrics',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            query: {
                'type': type,
                'key': key,
                'since_line': sinceLine,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Detect Run Metrics Sources
     * Classify foreign log formats under the run directory (read-only).
     *
     * Does not write the metrics buffer. Host ≠ MolRec: detection never invents
     * meta/status sections.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param molexpSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static detectRunMetricsSources1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/metrics/detect',
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
     * Ingest Run Metrics
     * Ingest foreign logs into the run host metrics surface (additive).
     *
     * Shares :func:`molexp.plugins.metrics_ingest.ingest_run` with the CLI.
     * Skips are returned; the route does not fail the whole call when one
     * converter cannot run.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param molexpSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static ingestRunMetrics1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/metrics/ingest',
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
     * Rerun Run
     * Rerun a failed/cancelled run in a new execution (no clone).
     *
     * A fresh ``exec-{run_id}-N`` is derived and, for a targeted run, dispatched
     * through molq; no parameters are cloned and no new Run is created. Note the
     * content-addressed cache may still serve deterministic tasks — pass
     * ``fresh=true`` to bypass cache reads (persisted as a marker in the new
     * execution slot, so whichever process executes it honors the request).
     * 409 unless the run is failed/cancelled (pending/succeeded/running are not
     * rerun's job). A stale ``running`` run with a dead owner is reaped to
     * ``failed`` first (run-recovery bug 5).
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param fresh Bypass content-addressed cache reads for the new execution: every task body actually re-runs (results are still written back to the cache). Same capability as the CLI's `molexp run --rerun --fresh`.
     * @param molexpSession
     * @returns RunContinueResponse Successful Response
     * @throws ApiError
     */
    public static rerunRun1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        fresh: boolean = false,
        molexpSession?: (string | null),
    ): CancelablePromise<RunContinueResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/rerun',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            query: {
                'fresh': fresh,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Resume Run
     * Resume a failed/cancelled run: reopen its last non-succeeded execution.
     *
     * The reopened execution is re-dispatched on the same ``execution_id``; the
     * worker seeds already-completed nodes from disk and recomputes the rest.
     * 409 unless the run is failed/cancelled (pending/succeeded/running are not
     * resume's job). A stale ``running`` run with a dead owner is reaped to
     * ``failed`` first, so it enters the retryable domain instead of 409-ing
     * forever (run-recovery bug 5).
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param molexpSession
     * @returns RunContinueResponse Successful Response
     * @throws ApiError
     */
    public static resumeRun1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<RunContinueResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/resume',
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
     * Start Run
     * Start a pending run by dispatching it to a compute target (the ``run`` verb).
     *
     * The disjoint counterpart to resume/rerun: ``run`` owns ``pending`` runs only
     * (409 otherwise — retrying a failed/cancelled run is resume/rerun's job, and a
     * live ``running`` run must not get a second execution). A pending run is
     * target-less (the create+dispatch contract dispatches a targeted run on
     * create), so Start supplies the target to execute on; a target-less Start
     * (no body target, none recorded) 422s — those run via ``molexp run`` on the
     * host, since the server never executes a workflow in-process.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param requestBody
     * @param molexpSession
     * @returns RunContinueResponse Successful Response
     * @throws ApiError
     */
    public static startRun1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        requestBody: RunStartRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<RunContinueResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/run',
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
     * Update Run Status
     * Mark a run ``cancelled`` — the one status a client may write directly.
     *
     * Every other status is owned by the run lifecycle (the three-verb law):
     * ``running``/``succeeded``/``failed`` are stamped by the executing
     * process, never by a client, and retrying goes through the explicit
     * ``resume``/``rerun`` routes. Requests for any status but ``cancelled``
     * are refused with 409; prefer ``POST .../{run_id}/cancel`` (which also
     * signals the live executor) over this raw mark.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param requestBody
     * @param molexpSession
     * @returns RunStatusResponse Successful Response
     * @throws ApiError
     */
    public static updateRunStatus1(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        requestBody: RunStatusUpdateRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<RunStatusResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/status',
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
    public static createRun3(
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
