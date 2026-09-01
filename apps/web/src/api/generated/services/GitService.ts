/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GitCheckpointResponse } from '../models/GitCheckpointResponse';
import type { GitPushRequest } from '../models/GitPushRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class GitService {
    /**
     * Git Checkpoint Route
     * @param molexpSession
     * @returns GitCheckpointResponse Successful Response
     * @throws ApiError
     */
    public static gitCheckpointRoute(
        molexpSession?: (string | null),
    ): CancelablePromise<GitCheckpointResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/git/checkpoint',
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Git Push Route
     * @param requestBody
     * @param molexpSession
     * @returns string Successful Response
     * @throws ApiError
     */
    public static gitPushRoute(
        requestBody: GitPushRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/git/push',
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
     * Git Rebuild Route
     * @param molexpSession
     * @returns GitCheckpointResponse Successful Response
     * @throws ApiError
     */
    public static gitRebuildRoute(
        molexpSession?: (string | null),
    ): CancelablePromise<GitCheckpointResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/git/rebuild',
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Git Checkpoint Route
     * @param ws
     * @param molexpSession
     * @returns GitCheckpointResponse Successful Response
     * @throws ApiError
     */
    public static gitCheckpointRouteWs(
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<GitCheckpointResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/git/checkpoint',
            path: {
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
     * Git Push Route
     * @param ws
     * @param requestBody
     * @param molexpSession
     * @returns string Successful Response
     * @throws ApiError
     */
    public static gitPushRouteWs(
        ws: string,
        requestBody: GitPushRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/git/push',
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
    /**
     * Git Rebuild Route
     * @param ws
     * @param molexpSession
     * @returns GitCheckpointResponse Successful Response
     * @throws ApiError
     */
    public static gitRebuildRouteWs(
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<GitCheckpointResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/git/rebuild',
            path: {
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
}
