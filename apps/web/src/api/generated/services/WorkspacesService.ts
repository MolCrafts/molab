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
     * List the workspaces ``molexp serve`` was started with.
     *
     * A remote workspace whose transport is currently unreachable is still
     * listed, flagged ``unreachable`` so the UI can degrade gracefully rather
     * than failing the whole list.  ``needsAuth`` is true for unreachable
     * remotes so the UI can open a verification-code dialog.
     *
     * When auth is enabled, the list is filtered by the user's workspace allowlist.
     * @param molexpSession
     * @returns ServedWorkspaceResponse Successful Response
     * @throws ApiError
     */
    public static listWorkspaces(
        molexpSession?: (string | null),
    ): CancelablePromise<Array<ServedWorkspaceResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces',
            cookies: {
                'molexp_session': molexpSession,
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
     * (``kind=remote`` with registry ``name`` / ``@name`` / ``Host:/abs`` path).
     * Optional ``activate`` switches the active workspace to the new root.
     * @param requestBody
     * @param molexpSession
     * @returns ServedWorkspaceResponse Successful Response
     * @throws ApiError
     */
    public static addWorkspace(
        requestBody: WorkspaceAddRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<ServedWorkspaceResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/add',
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
     * Remove Workspace
     * VS Code ``Remove Folder from Workspace`` — drop a root from the served set.
     *
     * Does not delete files on disk. When the removed root was active, the first
     * remaining served workspace becomes active (if any).
     * @param key
     * @param molexpSession
     * @returns ServedWorkspaceResponse Successful Response
     * @throws ApiError
     */
    public static removeWorkspace(
        key: string,
        molexpSession?: (string | null),
    ): CancelablePromise<Array<ServedWorkspaceResponse>> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/workspaces/{key}',
            path: {
                'key': key,
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
     * Connect Workspace
     * Submit a verification code and open an SSH ControlMaster for *key*.
     *
     * Headless path for 2FA hosts: the server process has no TTY, so it feeds
     * *code* to OpenSSH via ``SSH_ASKPASS``.  After success, BatchMode ops
     * reuse the multiplex socket (see ``ControlPersist`` in ``~/.ssh/config``).
     *
     * The in-process workspace cache is cleared so the next API call re-probes
     * the remote root with the live master.
     * @param key
     * @param requestBody
     * @param molexpSession
     * @returns WorkspaceConnectResponse Successful Response
     * @throws ApiError
     */
    public static connectWorkspace(
        key: string,
        requestBody: WorkspaceConnectRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<WorkspaceConnectResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{key}/connect',
            path: {
                'key': key,
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
