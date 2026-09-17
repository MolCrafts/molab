/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CacheClearResponse } from '../models/CacheClearResponse';
import type { CacheControlRequest } from '../models/CacheControlRequest';
import type { CacheControlResponse } from '../models/CacheControlResponse';
import type { CacheStatsResponse } from '../models/CacheStatsResponse';
import type { CacheStatusResponse } from '../models/CacheStatusResponse';
import type { CurateRequest } from '../models/CurateRequest';
import type { CurateResponse } from '../models/CurateResponse';
import type { DirectoryCreateRequest } from '../models/DirectoryCreateRequest';
import type { FileContentResponse } from '../models/FileContentResponse';
import type { FileContentUpdateRequest } from '../models/FileContentUpdateRequest';
import type { TargetTestResponse } from '../models/TargetTestResponse';
import type { WorkspaceContextResponse } from '../models/WorkspaceContextResponse';
import type { WorkspaceInfoResponse } from '../models/WorkspaceInfoResponse';
import type { WorkspaceOpenLocalRequest } from '../models/WorkspaceOpenLocalRequest';
import type { WorkspaceOpenRemoteRequest } from '../models/WorkspaceOpenRemoteRequest';
import type { WorkspaceRunsResponse } from '../models/WorkspaceRunsResponse';
import type { WorkspaceSummaryResponse } from '../models/WorkspaceSummaryResponse';
import type { WorkspaceTargetCreateRequest } from '../models/WorkspaceTargetCreateRequest';
import type { WorkspaceTargetListResponse } from '../models/WorkspaceTargetListResponse';
import type { WorkspaceTargetResponse } from '../models/WorkspaceTargetResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class WorkspaceService {
    /**
     * Curate Workspace
     * Gate + execute one deterministic destructive-curation op (single stack).
     *
     * Shares the ``run_curation_proposal`` backend with ``molab curate`` (Python ≡
     * UI). ``approve=false`` (default) records the proposal and refuses; ``true``
     * executes the mutation. Either way the §8 ``change_proposal`` artifact is the audit.
     * @param requestBody
     * @param molabSession
     * @returns CurateResponse Successful Response
     * @throws ApiError
     */
    public static curateWorkspace(
        requestBody: CurateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<CurateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspace/curate',
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
     * Get Cache Stats
     * Workspace content-addressed task cache statistics.
     * @param molabSession
     * @returns CacheStatsResponse Successful Response
     * @throws ApiError
     */
    public static getCacheStats(
        molabSession?: (string | null),
    ): CancelablePromise<CacheStatsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspace/cache/stats',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Clear Cache
     * Clear the workspace content-addressed task cache.
     * @param molabSession
     * @returns CacheClearResponse Successful Response
     * @throws ApiError
     */
    public static clearCache(
        molabSession?: (string | null),
    ): CancelablePromise<CacheClearResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/workspace/cache',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Workspace Info
     * Get workspace information.
     * @param molabSession
     * @returns WorkspaceInfoResponse Successful Response
     * @throws ApiError
     */
    public static getWorkspaceInfo(
        molabSession?: (string | null),
    ): CancelablePromise<WorkspaceInfoResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspace/info',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Workspace Context
     * The canonical structural workspace read-model (integration.md §1).
     *
     * A read-only projection assembled from authoritative workspace state — the one
     * shape agents/planners/CLI/UI observe. ``ContextFocus`` is supplied by the
     * caller via optional query params and is never persisted. ``/runs`` remains the
     * specialized detailed run view (richer per-execution rows); this endpoint is the
     * canonical *structure* and stays consistent with it.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param molabSession
     * @returns WorkspaceContextResponse Successful Response
     * @throws ApiError
     */
    public static getWorkspaceContext(
        projectId?: (string | null),
        experimentId?: (string | null),
        runId?: (string | null),
        molabSession?: (string | null),
    ): CancelablePromise<WorkspaceContextResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspace/context',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'projectId': projectId,
                'experimentId': experimentId,
                'runId': runId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Workspace Copilot
     * The read-only Workspace Copilot summary — structured state + ranked next-actions.
     *
     * A pure projection over the canonical ``WorkspaceContext``; it mutates nothing.
     * Next-actions are **advisory** and separated from execution — a mutating one
     * names the operation it would perform in ``op``, and whoever executes it owns
     * the policy for what that operation requires.
     * @param molabSession
     * @returns WorkspaceSummaryResponse Successful Response
     * @throws ApiError
     */
    public static getWorkspaceCopilot(
        molabSession?: (string | null),
    ): CancelablePromise<WorkspaceSummaryResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspace/copilot',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Workspace Runs
     * Cross-experiment list of runs, each with embedded execution attempts.
     *
     * Returns rows ordered by ``created_at`` desc.  Plugins surface
     * backend-specific columns (cluster, scheduler job id, etc.) via the
     * ``backend`` / ``backendMetadata`` fields on each execution row.
     * @param projectId
     * @param experimentId
     * @param backend Filter by executor backend
     * @param status Filter by contained Execution status
     * @param offset
     * @param limit
     * @param molabSession
     * @returns WorkspaceRunsResponse Successful Response
     * @throws ApiError
     */
    public static listWorkspaceRuns(
        projectId?: (string | null),
        experimentId?: (string | null),
        backend?: (string | null),
        status?: (string | null),
        offset?: number,
        limit: number = 500,
        molabSession?: (string | null),
    ): CancelablePromise<WorkspaceRunsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspace/runs',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'projectId': projectId,
                'experimentId': experimentId,
                'backend': backend,
                'status': status,
                'offset': offset,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Workspace Files
     * Return a nested file tree rooted at the requested path.
     *
     * Routes through ``workspace.fs`` so remote workspaces (and the
     * :class:`CachedRemoteFileSystem` mirror) work the same as local ones.
     *
     * With ``include=catalog``, file nodes that match a registered asset
     * are enriched with ``assetId``, ``assetKind``, ``producerRunId`` and
     * ``producerTaskId`` so the UI can render lineage chips inline.
     *
     * Children matching the workspace ``.gitignore`` cascade (plus a safety
     * floor for ``node_modules`` / ``.git`` / venvs) are omitted so git-managed
     * workspaces do not dump dependency trees into the UI.
     * @param path Workspace-relative path to list
     * @param maxDepth Maximum recursion depth
     * @param include Comma-separated optional enrichments (e.g. 'catalog')
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static listWorkspaceFiles(
        path: string = '',
        maxDepth: number = 4,
        include?: (string | null),
        molabSession?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspace/files',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'path': path,
                'max_depth': maxDepth,
                'include': include,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Write File
     * Create or update a file in the workspace.
     * @param requestBody
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static writeFile(
        requestBody: FileContentUpdateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/workspace/files',
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
     * Read Workspace File
     * Read a text file from the workspace.
     *
     * Routes through ``workspace.fs`` so remote workspaces (and the
     * :class:`CachedRemoteFileSystem` mirror) take effect.
     * @param path Workspace-relative path to read
     * @param molabSession
     * @returns FileContentResponse Successful Response
     * @throws ApiError
     */
    public static readWorkspaceFile(
        path: string = '',
        molabSession?: (string | null),
    ): CancelablePromise<FileContentResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspace/file',
            cookies: {
                'molab_session': molabSession,
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
     * Read Workspace File Blob
     * Read a binary file from the workspace.
     *
     * Routes through ``workspace.fs`` so remote workspaces (and the
     * :class:`CachedRemoteFileSystem` mirror) take effect.
     * @param path Workspace-relative path to read
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static readWorkspaceFileBlob(
        path: string = '',
        molabSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspace/file/blob',
            cookies: {
                'molab_session': molabSession,
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
     * Open Workspace
     * Set the active workspace — local path or registered remote descriptor.
     *
     * Switching the active workspace drains any registered workspace
     * subscribers (SSE streams, file watchers — registered via
     * :func:`~molab.server.dependencies.register_workspace_subscriber`)
     * *before* the cache is reset, so the new workspace starts from a
     * clean subscriber slate.
     * @param requestBody
     * @param molabSession
     * @returns WorkspaceInfoResponse Successful Response
     * @throws ApiError
     */
    public static openWorkspace(
        requestBody: (WorkspaceOpenLocalRequest | WorkspaceOpenRemoteRequest),
        molabSession?: (string | null),
    ): CancelablePromise<WorkspaceInfoResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspace/open',
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
     * Create Directory
     * Create a directory in the workspace.
     * @param requestBody
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static createDirectory(
        requestBody: DirectoryCreateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspace/directories',
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
     * List Workspace Targets
     * @param molabSession
     * @returns WorkspaceTargetListResponse Successful Response
     * @throws ApiError
     */
    public static listWorkspaceTargets(
        molabSession?: (string | null),
    ): CancelablePromise<WorkspaceTargetListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspace/targets',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Workspace Target
     * @param requestBody
     * @param molabSession
     * @returns WorkspaceTargetResponse Successful Response
     * @throws ApiError
     */
    public static createWorkspaceTarget(
        requestBody: WorkspaceTargetCreateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<WorkspaceTargetResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspace/targets',
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
     * Delete Workspace Target
     * @param name
     * @param molabSession
     * @returns void
     * @throws ApiError
     */
    public static deleteWorkspaceTarget(
        name: string,
        molabSession?: (string | null),
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/workspace/targets/{name}',
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
     * Test Workspace Target
     * Connectivity probe for a workspace-target descriptor.
     *
     * Returns HTTP 200 with ``ok=False`` on probe failure (matches the
     * ``/api/targets/{name}/test`` pattern) so the UI can render failures
     * inline rather than parsing HTTP error envelopes.
     * @param name
     * @param molabSession
     * @returns TargetTestResponse Successful Response
     * @throws ApiError
     */
    public static testWorkspaceTarget(
        name: string,
        molabSession?: (string | null),
    ): CancelablePromise<TargetTestResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspace/targets/{name}/test',
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
     * Workspace Cache Status
     * Poll remote-index progress (file-count total → fetch done).
     *
     * Local workspaces return ``cached=false`` with idle progress. The UI
     * status strip polls this while ``phase`` is ``counting`` / ``fetching``.
     * @param molabSession
     * @returns CacheStatusResponse Successful Response
     * @throws ApiError
     */
    public static workspaceCacheStatus(
        molabSession?: (string | null),
    ): CancelablePromise<CacheStatusResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspace/cache/status',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Invalidate Workspace Cache
     * Drop cached entries from the active workspace's mirror.
     *
     * ``scope="indices"`` is the "I added a run on the remote, refresh
     * navigation" knob — it drops only entries whose basename identifies
     * a navigation-index file, leaving log/blob bytes intact.
     * @param requestBody
     * @param molabSession
     * @returns CacheControlResponse Successful Response
     * @throws ApiError
     */
    public static invalidateWorkspaceCache(
        requestBody: CacheControlRequest,
        molabSession?: (string | null),
    ): CancelablePromise<CacheControlResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspace/cache/invalidate',
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
     * Refresh Workspace Cache
     * Invalidate, then walk the navigation indices again.
     *
     * Saves the UI from issuing a follow-up call after a refresh button
     * click.  Per-node failures during the walk surface as ``warnings`` —
     * the response is still 200 so a single bad project does not blank
     * the whole tree.
     * @param requestBody
     * @param molabSession
     * @returns CacheControlResponse Successful Response
     * @throws ApiError
     */
    public static refreshWorkspaceCache(
        requestBody: CacheControlRequest,
        molabSession?: (string | null),
    ): CancelablePromise<CacheControlResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspace/cache/refresh',
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
