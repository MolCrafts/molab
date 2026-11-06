/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HistoryFact } from '../models/HistoryFact';
import type { HistoryPushRequest } from '../models/HistoryPushRequest';
import type { HistorySyncResponse } from '../models/HistorySyncResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class HistoryService {
    /**
     * Read History
     * List recorded facts, newest first.
     * @param entity
     * @param event
     * @param limit
     * @param molabSession
     * @returns HistoryFact Successful Response
     * @throws ApiError
     */
    public static readHistory(
        entity?: (string | null),
        event?: (string | null),
        limit: number = 50,
        molabSession?: (string | null),
    ): CancelablePromise<Array<HistoryFact>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/history',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'entity': entity,
                'event': event,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Sync History
     * Commit anything a worker left uncommitted.
     * @param molabSession
     * @returns HistorySyncResponse Successful Response
     * @throws ApiError
     */
    public static syncHistory(
        molabSession?: (string | null),
    ): CancelablePromise<HistorySyncResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/history/sync',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Push History
     * Push the workspace history to a remote — this is the backup.
     * @param requestBody
     * @param molabSession
     * @returns HistorySyncResponse Successful Response
     * @throws ApiError
     */
    public static pushHistory(
        requestBody: HistoryPushRequest,
        molabSession?: (string | null),
    ): CancelablePromise<HistorySyncResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/history/push',
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
     * Read History
     * List recorded facts, newest first.
     * @param ws
     * @param entity
     * @param event
     * @param limit
     * @param molabSession
     * @returns HistoryFact Successful Response
     * @throws ApiError
     */
    public static readHistoryWs(
        ws: string,
        entity?: (string | null),
        event?: (string | null),
        limit: number = 50,
        molabSession?: (string | null),
    ): CancelablePromise<Array<HistoryFact>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/history',
            path: {
                'ws': ws,
            },
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'entity': entity,
                'event': event,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Sync History
     * Commit anything a worker left uncommitted.
     * @param ws
     * @param molabSession
     * @returns HistorySyncResponse Successful Response
     * @throws ApiError
     */
    public static syncHistoryWs(
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<HistorySyncResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/history/sync',
            path: {
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
     * Push History
     * Push the workspace history to a remote — this is the backup.
     * @param ws
     * @param requestBody
     * @param molabSession
     * @returns HistorySyncResponse Successful Response
     * @throws ApiError
     */
    public static pushHistoryWs(
        ws: string,
        requestBody: HistoryPushRequest,
        molabSession?: (string | null),
    ): CancelablePromise<HistorySyncResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/history/push',
            path: {
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
}
