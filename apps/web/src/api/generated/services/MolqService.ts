/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MolqJobDetailResponse } from '../models/MolqJobDetailResponse';
import type { MolqJobsResponse } from '../models/MolqJobsResponse';
import type { MolqTargetListResponse } from '../models/MolqTargetListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class MolqService {
    /**
     * List Targets
     * List configured molq targets (one per profile in ``~/.molq/config.yaml``).
     * @param molabSession
     * @returns MolqTargetListResponse Successful Response
     * @throws ApiError
     */
    public static listTargets(
        molabSession?: (string | null),
    ): CancelablePromise<MolqTargetListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/plugins/molq/targets',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Jobs
     * List jobs across one or all targets, plus aggregate queue stats.
     * @param target Profile name to filter by.
     * @param includeTerminal
     * @param limit
     * @param molabSession
     * @returns MolqJobsResponse Successful Response
     * @throws ApiError
     */
    public static listJobs(
        target?: (string | null),
        includeTerminal: boolean = true,
        limit: number = 200,
        molabSession?: (string | null),
    ): CancelablePromise<MolqJobsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/plugins/molq/jobs',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'target': target,
                'includeTerminal': includeTerminal,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Job
     * Return a single job's detail including transitions and dependency state.
     * @param jobId
     * @param target Profile name owning the job.
     * @param molabSession
     * @returns MolqJobDetailResponse Successful Response
     * @throws ApiError
     */
    public static getJob(
        jobId: string,
        target: string,
        molabSession?: (string | null),
    ): CancelablePromise<MolqJobDetailResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/plugins/molq/jobs/{job_id}',
            path: {
                'job_id': jobId,
            },
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'target': target,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Stream Logs
     * SSE stream of newline-terminated log chunks.
     *
     * Each event payload is ``data: {"line": "..."}\n\n`` so the client's
     * EventSource ``message`` handler parses one log line per event.
     * @param jobId
     * @param target Profile name owning the job.
     * @param stream
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static streamLogs(
        jobId: string,
        target: string,
        stream: string = 'stdout',
        molabSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/plugins/molq/jobs/{job_id}/logs',
            path: {
                'job_id': jobId,
            },
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'target': target,
                'stream': stream,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
