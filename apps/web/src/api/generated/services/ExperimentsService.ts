/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ExperimentComparisonResponse } from '../models/ExperimentComparisonResponse';
import type { ExperimentCreateRequest } from '../models/ExperimentCreateRequest';
import type { ExperimentResponse } from '../models/ExperimentResponse';
import type { MessageResponse } from '../models/MessageResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ExperimentsService {
    /**
     * List Experiments
     * @param projectId
     * @param molabSession
     * @returns ExperimentResponse Successful Response
     * @throws ApiError
     */
    public static listExperiments(
        projectId: string,
        molabSession?: (string | null),
    ): CancelablePromise<Array<ExperimentResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments',
            path: {
                'project_id': projectId,
            },
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Experiment
     * @param projectId
     * @param requestBody
     * @param molabSession
     * @returns ExperimentResponse Successful Response
     * @throws ApiError
     */
    public static createExperiment(
        projectId: string,
        requestBody: ExperimentCreateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<ExperimentResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/experiments',
            path: {
                'project_id': projectId,
            },
            cookies: {
                'molab_session': molabSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Experiment
     * @param projectId
     * @param experimentId
     * @param molabSession
     * @returns ExperimentResponse Successful Response
     * @throws ApiError
     */
    public static getExperiment(
        projectId: string,
        experimentId: string,
        molabSession?: (string | null),
    ): CancelablePromise<ExperimentResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
            },
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Experiment
     * @param projectId
     * @param experimentId
     * @param molabSession
     * @returns MessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteExperiment(
        projectId: string,
        experimentId: string,
        molabSession?: (string | null),
    ): CancelablePromise<MessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/projects/{project_id}/experiments/{experiment_id}',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
            },
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Experiment Comparison
     * Compare immutable logical Run definitions.
     *
     * Execution outcomes are intentionally absent: callers must select explicit
     * Execution identities before comparing observed metrics or results.
     * @param projectId
     * @param experimentId
     * @param molabSession
     * @returns ExperimentComparisonResponse Successful Response
     * @throws ApiError
     */
    public static getExperimentComparison(
        projectId: string,
        experimentId: string,
        molabSession?: (string | null),
    ): CancelablePromise<ExperimentComparisonResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/comparison',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
            },
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Experiments
     * @param projectId
     * @param ws
     * @param molabSession
     * @returns ExperimentResponse Successful Response
     * @throws ApiError
     */
    public static listExperimentsWs(
        projectId: string,
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<Array<ExperimentResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments',
            path: {
                'project_id': projectId,
                'ws': ws,
            },
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Experiment
     * @param projectId
     * @param ws
     * @param requestBody
     * @param molabSession
     * @returns ExperimentResponse Successful Response
     * @throws ApiError
     */
    public static createExperimentWs(
        projectId: string,
        ws: string,
        requestBody: ExperimentCreateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<ExperimentResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments',
            path: {
                'project_id': projectId,
                'ws': ws,
            },
            cookies: {
                'molab_session': molabSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Experiment
     * @param projectId
     * @param experimentId
     * @param ws
     * @param molabSession
     * @returns ExperimentResponse Successful Response
     * @throws ApiError
     */
    public static getExperimentWs(
        projectId: string,
        experimentId: string,
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<ExperimentResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'ws': ws,
            },
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Experiment
     * @param projectId
     * @param experimentId
     * @param ws
     * @param molabSession
     * @returns MessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteExperimentWs(
        projectId: string,
        experimentId: string,
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<MessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'ws': ws,
            },
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Experiment Comparison
     * Compare immutable logical Run definitions.
     *
     * Execution outcomes are intentionally absent: callers must select explicit
     * Execution identities before comparing observed metrics or results.
     * @param projectId
     * @param experimentId
     * @param ws
     * @param molabSession
     * @returns ExperimentComparisonResponse Successful Response
     * @throws ApiError
     */
    public static getExperimentComparisonWs(
        projectId: string,
        experimentId: string,
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<ExperimentComparisonResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/comparison',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'ws': ws,
            },
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
