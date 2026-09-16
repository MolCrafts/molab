/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LammpsLogResponse } from '../models/LammpsLogResponse';
import type { RunActionResponse } from '../models/RunActionResponse';
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
import type { WorkspaceEventResponse } from '../models/WorkspaceEventResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class RunsService {
    /**
     * List Runs
     * @param projectId
     * @param experimentId
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static listRunsApiProjectsProjectIdExperimentsExperimentIdRunsGet(
        projectId: string,
        experimentId: string,
    ): CancelablePromise<Array<RunResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
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
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static createRunApiProjectsProjectIdExperimentsExperimentIdRunsPost(
        projectId: string,
        experimentId: string,
        requestBody: RunCreateRequest,
    ): CancelablePromise<RunResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
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
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static getRunApiProjectsProjectIdExperimentsExperimentIdRunsRunIdGet(
        projectId: string,
        experimentId: string,
        runId: string,
    ): CancelablePromise<RunResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
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
     * Routes through :func:`molexp.plugins.submit_molq.cancel.try_cancel`, which signals
     * molq via :class:`molq.Submitor` for cluster-submitted runs and
     * sends ``SIGTERM`` for runs still owned by a local pid.  When neither
     * path applies (run never submitted, terminal, or executor info
     * missing) we fall back to flipping the metadata status so the UI
     * still reflects user intent.
     * @param projectId
     * @param experimentId
     * @param runId
     * @returns RunActionResponse Successful Response
     * @throws ApiError
     */
    public static cancelRunApiProjectsProjectIdExperimentsExperimentIdRunsRunIdCancelPost(
        projectId: string,
        experimentId: string,
        runId: string,
    ): CancelablePromise<RunActionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/cancel',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * @returns WorkspaceEventResponse Successful Response
     * @throws ApiError
     */
    public static getRunEventsApiProjectsProjectIdExperimentsExperimentIdRunsRunIdEventsGet(
        projectId: string,
        experimentId: string,
        runId: string,
        limit: number = 50,
    ): CancelablePromise<Array<WorkspaceEventResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/events',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * @returns RunExecutionResponse Successful Response
     * @throws ApiError
     */
    public static getRunExecutionApiProjectsProjectIdExperimentsExperimentIdRunsRunIdExecutionGet(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId?: (string | null),
    ): CancelablePromise<RunExecutionResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/execution',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * Return a stdout/stderr tail window for a specific execution attempt.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param maxBytes
     * @param sinceStdout
     * @param sinceStderr
     * @returns RunLogsResponse Successful Response
     * @throws ApiError
     */
    public static getRunExecutionLogsApiProjectsProjectIdExperimentsExperimentIdRunsRunIdExecutionsExecutionIdLogsGet(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        maxBytes: number = 256000,
        sinceStdout?: (number | null),
        sinceStderr?: (number | null),
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
            query: {
                'max_bytes': maxBytes,
                'since_stdout': sinceStdout,
                'since_stderr': sinceStderr,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Export Run
     * Stream a zip archive of the run directory (artifacts, logs, metadata).
     *
     * Genuinely streamed: the archive is produced chunk by chunk, so exporting a
     * run with gigabytes of trajectories never sizes the server's memory to the
     * run. Above :data:`EXPORT_MAX_BYTES` the request is refused outright rather
     * than tying up a worker for minutes.
     * @param projectId
     * @param experimentId
     * @param runId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static exportRunApiProjectsProjectIdExperimentsExperimentIdRunsRunIdExportGet(
        projectId: string,
        experimentId: string,
        runId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/export',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run File Text
     * Return a bounded text window over a file under the run directory.
     *
     * Defaults to the *head* — a source or config viewer reads from the top —
     * and to the largest window the server will emit, so small files come back
     * whole exactly as before.  Page with ``since_offset=end``.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param path Relative path under run_dir
     * @param mode
     * @param maxBytes
     * @param sinceOffset
     * @returns RunFileTextResponse Successful Response
     * @throws ApiError
     */
    public static getRunFileTextApiProjectsProjectIdExperimentsExperimentIdRunsRunIdFileTextGet(
        projectId: string,
        experimentId: string,
        runId: string,
        path: string,
        mode: 'head' | 'tail' = 'head',
        maxBytes: number = 2000000,
        sinceOffset?: (number | null),
    ): CancelablePromise<RunFileTextResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/file/text',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            query: {
                'path': path,
                'mode': mode,
                'max_bytes': maxBytes,
                'since_offset': sinceOffset,
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
     * Files registered in the asset catalog (artifacts, logs, checkpoints,
     * error traces) carry ``assetId``, ``assetKind``, and ``taskId`` so the
     * UI can render lineage chips inline.
     *
     * The walk is bounded in both directions: ``max_depth`` levels down, and
     * ``max_entries`` children per directory. A run that wrote 100k frames into
     * one directory therefore costs a bounded response; the containing folder
     * node reports ``entryCount`` and ``truncated`` so the UI can say so.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param maxDepth
     * @param maxEntries
     * @returns RunFilesResponse Successful Response
     * @throws ApiError
     */
    public static getRunFilesApiProjectsProjectIdExperimentsExperimentIdRunsRunIdFilesGet(
        projectId: string,
        experimentId: string,
        runId: string,
        maxDepth: number = 6,
        maxEntries: number = 2000,
    ): CancelablePromise<RunFilesResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/files',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            query: {
                'max_depth': maxDepth,
                'max_entries': maxEntries,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Harvest Run Route
     * Harvest a terminal run into a sourced KnowledgeItem under its experiment.
     *
     * Harvest reads the run's outputs and writes a Concept, so it is
     * filesystem-bound; it runs on the heavy pool to keep the shared request
     * threads free for cheap reads.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param requestBody
     * @returns string Successful Response
     * @throws ApiError
     */
    public static harvestRunRouteApiProjectsProjectIdExperimentsExperimentIdRunsRunIdHarvestPost(
        projectId: string,
        experimentId: string,
        runId: string,
        requestBody: RunHarvestRequest,
    ): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/harvest',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * @returns RunActionResponse Successful Response
     * @throws ApiError
     */
    public static cancelRunApiProjectsProjectIdExperimentsExperimentIdRunsRunIdKillPost(
        projectId: string,
        experimentId: string,
        runId: string,
    ): CancelablePromise<RunActionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/kill',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     *
     * A production MD log can be gigabytes; above
     * :data:`LAMMPS_LOG_MAX_BYTES` only the tail is parsed (the latest stages,
     * which is what a progress view wants) and ``truncated`` is set. Reading
     * and regexing the file is CPU- and IO-bound, so it runs on the heavy pool
     * rather than the shared request threads.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param path Relative path of the log file under run_dir
     * @returns LammpsLogResponse Successful Response
     * @throws ApiError
     */
    public static getRunLammpsLogApiProjectsProjectIdExperimentsExperimentIdRunsRunIdLammpsLogGet(
        projectId: string,
        experimentId: string,
        runId: string,
        path: string,
    ): CancelablePromise<LammpsLogResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/lammps-log',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * Return a stdout/stderr tail window for the most recent execution.
     *
     * Poll incrementally by passing the previous response's ``stdout_end`` /
     * ``stderr_end`` back as ``since_stdout`` / ``since_stderr``.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param maxBytes
     * @param sinceStdout
     * @param sinceStderr
     * @returns RunLogsResponse Successful Response
     * @throws ApiError
     */
    public static getRunLogsApiProjectsProjectIdExperimentsExperimentIdRunsRunIdLogsGet(
        projectId: string,
        experimentId: string,
        runId: string,
        maxBytes: number = 256000,
        sinceStdout?: (number | null),
        sinceStderr?: (number | null),
    ): CancelablePromise<RunLogsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/logs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            query: {
                'max_bytes': maxBytes,
                'since_stdout': sinceStdout,
                'since_stderr': sinceStderr,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run Metrics
     * Return run-local metrics from ``metrics/metrics.jsonl``.
     *
     * A live chart should follow by passing the previous ``nextOffset`` back as
     * ``since_offset``: that seeks straight to the appended bytes instead of
     * re-reading the stream from line 0 on every poll.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param type
     * @param key
     * @param sinceLine Legacy cursor; prefer since_offset.
     * @param sinceOffset Byte cursor from a previous nextOffset (O(1) resume).
     * @param maxScanBytes
     * @param limit
     * @returns RunMetricsResponse Successful Response
     * @throws ApiError
     */
    public static getRunMetricsApiProjectsProjectIdExperimentsExperimentIdRunsRunIdMetricsGet(
        projectId: string,
        experimentId: string,
        runId: string,
        type?: (string | null),
        key?: (string | null),
        sinceLine?: number,
        sinceOffset?: (number | null),
        maxScanBytes: number = 8388608,
        limit: number = 5000,
    ): CancelablePromise<RunMetricsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/metrics',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
            },
            query: {
                'type': type,
                'key': key,
                'since_line': sinceLine,
                'since_offset': sinceOffset,
                'max_scan_bytes': maxScanBytes,
                'limit': limit,
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
     * @returns RunContinueResponse Successful Response
     * @throws ApiError
     */
    public static rerunRunApiProjectsProjectIdExperimentsExperimentIdRunsRunIdRerunPost(
        projectId: string,
        experimentId: string,
        runId: string,
        fresh: boolean = false,
    ): CancelablePromise<RunContinueResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/rerun',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * @returns RunContinueResponse Successful Response
     * @throws ApiError
     */
    public static resumeRunApiProjectsProjectIdExperimentsExperimentIdRunsRunIdResumePost(
        projectId: string,
        experimentId: string,
        runId: string,
    ): CancelablePromise<RunContinueResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/resume',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * @returns RunContinueResponse Successful Response
     * @throws ApiError
     */
    public static startRunApiProjectsProjectIdExperimentsExperimentIdRunsRunIdRunPost(
        projectId: string,
        experimentId: string,
        runId: string,
        requestBody: RunStartRequest,
    ): CancelablePromise<RunContinueResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/run',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * @param projectId
     * @param experimentId
     * @param runId
     * @param requestBody
     * @returns RunStatusResponse Successful Response
     * @throws ApiError
     */
    public static updateRunStatusApiProjectsProjectIdExperimentsExperimentIdRunsRunIdStatusPatch(
        projectId: string,
        experimentId: string,
        runId: string,
        requestBody: Record<string, string>,
    ): CancelablePromise<RunStatusResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/status',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'run_id': runId,
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
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static listRunsApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsGet(
        projectId: string,
        experimentId: string,
        ws: string,
    ): CancelablePromise<Array<RunResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'ws': ws,
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
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static createRunApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsPost(
        projectId: string,
        experimentId: string,
        ws: string,
        requestBody: RunCreateRequest,
    ): CancelablePromise<RunResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/runs',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'ws': ws,
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
     * @returns RunResponse Successful Response
     * @throws ApiError
     */
    public static getRunApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdGet(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
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
     * Routes through :func:`molexp.plugins.submit_molq.cancel.try_cancel`, which signals
     * molq via :class:`molq.Submitor` for cluster-submitted runs and
     * sends ``SIGTERM`` for runs still owned by a local pid.  When neither
     * path applies (run never submitted, terminal, or executor info
     * missing) we fall back to flipping the metadata status so the UI
     * still reflects user intent.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @returns RunActionResponse Successful Response
     * @throws ApiError
     */
    public static cancelRunApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdCancelPost(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
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
     * @returns WorkspaceEventResponse Successful Response
     * @throws ApiError
     */
    public static getRunEventsApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdEventsGet(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        limit: number = 50,
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
     * @returns RunExecutionResponse Successful Response
     * @throws ApiError
     */
    public static getRunExecutionApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdExecutionGet(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        executionId?: (string | null),
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
     * Return a stdout/stderr tail window for a specific execution attempt.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param executionId
     * @param ws
     * @param maxBytes
     * @param sinceStdout
     * @param sinceStderr
     * @returns RunLogsResponse Successful Response
     * @throws ApiError
     */
    public static getRunExecutionLogsApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdExecutionsExecutionIdLogsGet(
        projectId: string,
        experimentId: string,
        runId: string,
        executionId: string,
        ws: string,
        maxBytes: number = 256000,
        sinceStdout?: (number | null),
        sinceStderr?: (number | null),
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
            query: {
                'max_bytes': maxBytes,
                'since_stdout': sinceStdout,
                'since_stderr': sinceStderr,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Export Run
     * Stream a zip archive of the run directory (artifacts, logs, metadata).
     *
     * Genuinely streamed: the archive is produced chunk by chunk, so exporting a
     * run with gigabytes of trajectories never sizes the server's memory to the
     * run. Above :data:`EXPORT_MAX_BYTES` the request is refused outright rather
     * than tying up a worker for minutes.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @returns any Successful Response
     * @throws ApiError
     */
    public static exportRunApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdExportGet(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
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
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run File Text
     * Return a bounded text window over a file under the run directory.
     *
     * Defaults to the *head* — a source or config viewer reads from the top —
     * and to the largest window the server will emit, so small files come back
     * whole exactly as before.  Page with ``since_offset=end``.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param path Relative path under run_dir
     * @param mode
     * @param maxBytes
     * @param sinceOffset
     * @returns RunFileTextResponse Successful Response
     * @throws ApiError
     */
    public static getRunFileTextApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdFileTextGet(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        path: string,
        mode: 'head' | 'tail' = 'head',
        maxBytes: number = 2000000,
        sinceOffset?: (number | null),
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
            query: {
                'path': path,
                'mode': mode,
                'max_bytes': maxBytes,
                'since_offset': sinceOffset,
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
     * Files registered in the asset catalog (artifacts, logs, checkpoints,
     * error traces) carry ``assetId``, ``assetKind``, and ``taskId`` so the
     * UI can render lineage chips inline.
     *
     * The walk is bounded in both directions: ``max_depth`` levels down, and
     * ``max_entries`` children per directory. A run that wrote 100k frames into
     * one directory therefore costs a bounded response; the containing folder
     * node reports ``entryCount`` and ``truncated`` so the UI can say so.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param maxDepth
     * @param maxEntries
     * @returns RunFilesResponse Successful Response
     * @throws ApiError
     */
    public static getRunFilesApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdFilesGet(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        maxDepth: number = 6,
        maxEntries: number = 2000,
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
            query: {
                'max_depth': maxDepth,
                'max_entries': maxEntries,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Harvest Run Route
     * Harvest a terminal run into a sourced KnowledgeItem under its experiment.
     *
     * Harvest reads the run's outputs and writes a Concept, so it is
     * filesystem-bound; it runs on the heavy pool to keep the shared request
     * threads free for cheap reads.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param requestBody
     * @returns string Successful Response
     * @throws ApiError
     */
    public static harvestRunRouteApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdHarvestPost(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        requestBody: RunHarvestRequest,
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
     * @returns RunActionResponse Successful Response
     * @throws ApiError
     */
    public static cancelRunApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdKillPost(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
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
     *
     * A production MD log can be gigabytes; above
     * :data:`LAMMPS_LOG_MAX_BYTES` only the tail is parsed (the latest stages,
     * which is what a progress view wants) and ``truncated`` is set. Reading
     * and regexing the file is CPU- and IO-bound, so it runs on the heavy pool
     * rather than the shared request threads.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param path Relative path of the log file under run_dir
     * @returns LammpsLogResponse Successful Response
     * @throws ApiError
     */
    public static getRunLammpsLogApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdLammpsLogGet(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        path: string,
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
     * Return a stdout/stderr tail window for the most recent execution.
     *
     * Poll incrementally by passing the previous response's ``stdout_end`` /
     * ``stderr_end`` back as ``since_stdout`` / ``since_stderr``.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param maxBytes
     * @param sinceStdout
     * @param sinceStderr
     * @returns RunLogsResponse Successful Response
     * @throws ApiError
     */
    public static getRunLogsApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdLogsGet(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        maxBytes: number = 256000,
        sinceStdout?: (number | null),
        sinceStderr?: (number | null),
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
            query: {
                'max_bytes': maxBytes,
                'since_stdout': sinceStdout,
                'since_stderr': sinceStderr,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Run Metrics
     * Return run-local metrics from ``metrics/metrics.jsonl``.
     *
     * A live chart should follow by passing the previous ``nextOffset`` back as
     * ``since_offset``: that seeks straight to the appended bytes instead of
     * re-reading the stream from line 0 on every poll.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param type
     * @param key
     * @param sinceLine Legacy cursor; prefer since_offset.
     * @param sinceOffset Byte cursor from a previous nextOffset (O(1) resume).
     * @param maxScanBytes
     * @param limit
     * @returns RunMetricsResponse Successful Response
     * @throws ApiError
     */
    public static getRunMetricsApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdMetricsGet(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        type?: (string | null),
        key?: (string | null),
        sinceLine?: number,
        sinceOffset?: (number | null),
        maxScanBytes: number = 8388608,
        limit: number = 5000,
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
            query: {
                'type': type,
                'key': key,
                'since_line': sinceLine,
                'since_offset': sinceOffset,
                'max_scan_bytes': maxScanBytes,
                'limit': limit,
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
     * @returns RunContinueResponse Successful Response
     * @throws ApiError
     */
    public static rerunRunApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdRerunPost(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        fresh: boolean = false,
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
     * @returns RunContinueResponse Successful Response
     * @throws ApiError
     */
    public static resumeRunApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdResumePost(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
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
     * @returns RunContinueResponse Successful Response
     * @throws ApiError
     */
    public static startRunApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdRunPost(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        requestBody: RunStartRequest,
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
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Run Status
     * @param projectId
     * @param experimentId
     * @param runId
     * @param ws
     * @param requestBody
     * @returns RunStatusResponse Successful Response
     * @throws ApiError
     */
    public static updateRunStatusApiWorkspacesWsProjectsProjectIdExperimentsExperimentIdRunsRunIdStatusPatch(
        projectId: string,
        experimentId: string,
        runId: string,
        ws: string,
        requestBody: Record<string, string>,
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
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
