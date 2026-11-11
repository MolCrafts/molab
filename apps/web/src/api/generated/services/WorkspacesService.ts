/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ServedWorkspaceResponse } from '../models/ServedWorkspaceResponse';
import type { WorkspaceAddRequest } from '../models/WorkspaceAddRequest';
import type { WorkspaceConnectRequest } from '../models/WorkspaceConnectRequest';
import type { WorkspaceConnectResponse } from '../models/WorkspaceConnectResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class WorkspacesService {
    /**
     * List Workspaces
     * List the workspaces ``molab serve`` was started with.
     *
     * A remote workspace whose transport is currently unreachable is still
     * listed, flagged ``unreachable`` so the UI can degrade gracefully rather
     * than failing the whole list. ``needsAuth`` identifies authentication failures;
     * network failures do not trigger a verification-code dialog.
     *
     * When auth is enabled, the list is filtered by the user's workspace allowlist.
     * @param molabSession
     * @returns ServedWorkspaceResponse Successful Response
     * @throws ApiError
     */
    public static listWorkspaces(
        molabSession?: (string | null),
    ): CancelablePromise<Array<ServedWorkspaceResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Add Workspace
     * VS Code ``Add Folder to Workspace`` — append a root to the live served set.
     *
     * Accepts a local absolute path (``kind=local``) or a remote descriptor
     * (``kind=remote`` with registry ``name`` / ``@name`` / ``cluster:/abs`` path).
     * Optional ``activate`` switches the active workspace to the new root.
     * @param requestBody
     * @param molabSession
     * @returns ServedWorkspaceResponse Successful Response
     * @throws ApiError
     */
    public static addWorkspace(
        requestBody: WorkspaceAddRequest,
        molabSession?: (string | null),
    ): CancelablePromise<ServedWorkspaceResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/add',
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
     * Remove Workspace
     * VS Code ``Remove Folder from Workspace`` — drop a root from the served set.
     *
     * Does not delete files on disk. When the removed root was active, the first
     * remaining served workspace becomes active (if any).
     * @param key
     * @param molabSession
     * @returns ServedWorkspaceResponse Successful Response
     * @throws ApiError
     */
    public static removeWorkspace(
        key: string,
        molabSession?: (string | null),
    ): CancelablePromise<Array<ServedWorkspaceResponse>> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/workspaces/{key}',
            path: {
                'key': key,
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
     * Connect Workspace
     * Authenticate through molq, then reopen the workspace with the same connection settings.
     * @param key
     * @param requestBody
     * @param molabSession
     * @returns WorkspaceConnectResponse Successful Response
     * @throws ApiError
     */
    public static connectWorkspace(
        key: string,
        requestBody: WorkspaceConnectRequest,
        molabSession?: (string | null),
    ): CancelablePromise<WorkspaceConnectResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{key}/connect',
            path: {
                'key': key,
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
