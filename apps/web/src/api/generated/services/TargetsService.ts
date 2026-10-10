/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TargetCreateRequest } from '../models/TargetCreateRequest';
import type { TargetListResponse } from '../models/TargetListResponse';
import type { TargetResponse } from '../models/TargetResponse';
import type { TargetTestResponse } from '../models/TargetTestResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class TargetsService {
    /**
     * List Targets Endpoint
     * List compute targets — the registered ones plus the built-in ``local``.
     * @param molabSession
     * @returns TargetListResponse Successful Response
     * @throws ApiError
     */
    public static listTargetsEndpoint(
        molabSession?: (string | null),
    ): CancelablePromise<TargetListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/targets',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Target Endpoint
     * Register a new compute target.
     *
     * Mirrors ``molab target add NAME --scratch ... [--host ...] [--scheduler ...]``.
     * @param requestBody
     * @param molabSession
     * @returns TargetResponse Successful Response
     * @throws ApiError
     */
    public static createTargetEndpoint(
        requestBody: TargetCreateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<TargetResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/targets',
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
     * Delete Target Endpoint
     * Remove the named compute target from the workspace registry.
     * @param name
     * @param molabSession
     * @returns void
     * @throws ApiError
     */
    public static deleteTargetEndpoint(
        name: string,
        molabSession?: (string | null),
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/targets/{name}',
            path: {
                'name': name,
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
     * Test Target Endpoint
     * Verify connectivity to a target — runs the same round-trip probe as
     * ``molab target test`` (true / mkdir scratch / 1-byte file round-trip).
     *
     * Returns ``ok=False`` with the failing step's detail rather than raising,
     * so the UI can render the failure inline.
     * @param name
     * @param molabSession
     * @returns TargetTestResponse Successful Response
     * @throws ApiError
     */
    public static testTargetEndpoint(
        name: string,
        molabSession?: (string | null),
    ): CancelablePromise<TargetTestResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/targets/{name}/test',
            path: {
                'name': name,
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
