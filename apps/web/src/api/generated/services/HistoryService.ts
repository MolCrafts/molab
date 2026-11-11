/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DocumentHistory } from '../models/DocumentHistory';
import type { HistoryFact } from '../models/HistoryFact';
import type { HistoryPushRequest } from '../models/HistoryPushRequest';
import type { HistorySyncResponse } from '../models/HistorySyncResponse';
import type { ReplayPage } from '../models/ReplayPage';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class HistoryService {
    /**
     * Read Document History
     * Read one knowledge file's Git revisions and compare with its working copy.
     * @param document
     * @param commit
     * @param limit
     * @param molabSession
     * @returns DocumentHistory Successful Response
     * @throws ApiError
     */
    public static readDocumentHistory(
        document: string,
        commit?: (string | null),
        limit: number = 50,
        molabSession?: (string | null),
    ): CancelablePromise<DocumentHistory> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/history/document',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'document': document,
                'commit': commit,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Replay History
     * Read the experimental sequence oldest first; never execute a step.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param kind
     * @param offset
     * @param limit
     * @param asOf
     * @param molabSession
     * @returns ReplayPage Successful Response
     * @throws ApiError
     */
    public static replayHistory(
        projectId?: (string | null),
        experimentId?: (string | null),
        runId?: (string | null),
        kind?: (string | null),
        offset?: number,
        limit: number = 100,
        asOf?: (string | null),
        molabSession?: (string | null),
    ): CancelablePromise<ReplayPage> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/history/replay',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'projectId': projectId,
                'experimentId': experimentId,
                'runId': runId,
                'kind': kind,
                'offset': offset,
                'limit': limit,
                'asOf': asOf,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Read Replay Document
     * The exact recorded document version, rendered as text by the caller.
     * @param commit
     * @param document
     * @param molabSession
     * @returns string Successful Response
     * @throws ApiError
     */
    public static readReplayDocument(
        commit: string,
        document: string,
        molabSession?: (string | null),
    ): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/history/replay/document',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'commit': commit,
                'document': document,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
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
     * Read Document History
     * Read one knowledge file's Git revisions and compare with its working copy.
     * @param ws
     * @param document
     * @param commit
     * @param limit
     * @param molabSession
     * @returns DocumentHistory Successful Response
     * @throws ApiError
     */
    public static readDocumentHistoryWs(
        ws: string,
        document: string,
        commit?: (string | null),
        limit: number = 50,
        molabSession?: (string | null),
    ): CancelablePromise<DocumentHistory> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/history/document',
            path: {
                'ws': ws,
            },
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'document': document,
                'commit': commit,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Replay History
     * Read the experimental sequence oldest first; never execute a step.
     * @param ws
     * @param projectId
     * @param experimentId
     * @param runId
     * @param kind
     * @param offset
     * @param limit
     * @param asOf
     * @param molabSession
     * @returns ReplayPage Successful Response
     * @throws ApiError
     */
    public static replayHistoryWs(
        ws: string,
        projectId?: (string | null),
        experimentId?: (string | null),
        runId?: (string | null),
        kind?: (string | null),
        offset?: number,
        limit: number = 100,
        asOf?: (string | null),
        molabSession?: (string | null),
    ): CancelablePromise<ReplayPage> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/history/replay',
            path: {
                'ws': ws,
            },
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'projectId': projectId,
                'experimentId': experimentId,
                'runId': runId,
                'kind': kind,
                'offset': offset,
                'limit': limit,
                'asOf': asOf,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Read Replay Document
     * The exact recorded document version, rendered as text by the caller.
     * @param ws
     * @param commit
     * @param document
     * @param molabSession
     * @returns string Successful Response
     * @throws ApiError
     */
    public static readReplayDocumentWs(
        ws: string,
        commit: string,
        document: string,
        molabSession?: (string | null),
    ): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/history/replay/document',
            path: {
                'ws': ws,
            },
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'commit': commit,
                'document': document,
            },
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
