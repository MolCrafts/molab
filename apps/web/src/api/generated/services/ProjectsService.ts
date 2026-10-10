/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AssetVersionResponse } from '../models/AssetVersionResponse';
import type { ManagedAssetResponse } from '../models/ManagedAssetResponse';
import type { MessageResponse } from '../models/MessageResponse';
import type { ProjectCreateRequest } from '../models/ProjectCreateRequest';
import type { ProjectResponse } from '../models/ProjectResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ProjectsService {
    /**
     * List Projects
     * @param molabSession
     * @returns ProjectResponse Successful Response
     * @throws ApiError
     */
    public static listProjects(
        molabSession?: (string | null),
    ): CancelablePromise<Array<ProjectResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Project
     * @param requestBody
     * @param molabSession
     * @returns ProjectResponse Successful Response
     * @throws ApiError
     */
    public static createProject(
        requestBody: ProjectCreateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<ProjectResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects',
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
     * Get Project
     * @param projectId
     * @param molabSession
     * @returns ProjectResponse Successful Response
     * @throws ApiError
     */
    public static getProject(
        projectId: string,
        molabSession?: (string | null),
    ): CancelablePromise<ProjectResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}',
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
     * Delete Project
     * @param projectId
     * @param molabSession
     * @returns MessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteProject(
        projectId: string,
        molabSession?: (string | null),
    ): CancelablePromise<MessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/projects/{project_id}',
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
     * List Project Assets
     * List long-lived Project data identities.
     * @param projectId
     * @param limit
     * @param molabSession
     * @returns ManagedAssetResponse Successful Response
     * @throws ApiError
     */
    public static listProjectAssets(
        projectId: string,
        limit: number = 100,
        molabSession?: (string | null),
    ): CancelablePromise<Array<ManagedAssetResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/assets',
            path: {
                'project_id': projectId,
            },
            cookies: {
                'molab_session': molabSession,
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
     * Get Project Asset
     * @param projectId
     * @param assetId
     * @param molabSession
     * @returns ManagedAssetResponse Successful Response
     * @throws ApiError
     */
    public static getProjectAsset(
        projectId: string,
        assetId: string,
        molabSession?: (string | null),
    ): CancelablePromise<ManagedAssetResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/assets/{asset_id}',
            path: {
                'project_id': projectId,
                'asset_id': assetId,
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
     * List Project Asset Versions
     * List immutable versions of a Project Asset.
     * @param projectId
     * @param assetId
     * @param molabSession
     * @returns AssetVersionResponse Successful Response
     * @throws ApiError
     */
    public static listProjectAssetVersions(
        projectId: string,
        assetId: string,
        molabSession?: (string | null),
    ): CancelablePromise<Array<AssetVersionResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/assets/{asset_id}/versions',
            path: {
                'project_id': projectId,
                'asset_id': assetId,
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
     * Download Project Asset
     * @param projectId
     * @param assetId
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadProjectAsset(
        projectId: string,
        assetId: string,
        molabSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/assets/{asset_id}/download',
            path: {
                'project_id': projectId,
                'asset_id': assetId,
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
     * List Projects
     * @param ws
     * @param molabSession
     * @returns ProjectResponse Successful Response
     * @throws ApiError
     */
    public static listProjectsWs(
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<Array<ProjectResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects',
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
     * Create Project
     * @param ws
     * @param requestBody
     * @param molabSession
     * @returns ProjectResponse Successful Response
     * @throws ApiError
     */
    public static createProjectWs(
        ws: string,
        requestBody: ProjectCreateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<ProjectResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects',
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
    /**
     * Get Project
     * @param projectId
     * @param ws
     * @param molabSession
     * @returns ProjectResponse Successful Response
     * @throws ApiError
     */
    public static getProjectWs(
        projectId: string,
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<ProjectResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}',
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
     * Delete Project
     * @param projectId
     * @param ws
     * @param molabSession
     * @returns MessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteProjectWs(
        projectId: string,
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<MessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/workspaces/{ws}/projects/{project_id}',
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
     * List Project Assets
     * List long-lived Project data identities.
     * @param projectId
     * @param ws
     * @param limit
     * @param molabSession
     * @returns ManagedAssetResponse Successful Response
     * @throws ApiError
     */
    public static listProjectAssetsWs(
        projectId: string,
        ws: string,
        limit: number = 100,
        molabSession?: (string | null),
    ): CancelablePromise<Array<ManagedAssetResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/assets',
            path: {
                'project_id': projectId,
                'ws': ws,
            },
            cookies: {
                'molab_session': molabSession,
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
     * Get Project Asset
     * @param projectId
     * @param assetId
     * @param ws
     * @param molabSession
     * @returns ManagedAssetResponse Successful Response
     * @throws ApiError
     */
    public static getProjectAssetWs(
        projectId: string,
        assetId: string,
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<ManagedAssetResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/assets/{asset_id}',
            path: {
                'project_id': projectId,
                'asset_id': assetId,
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
     * List Project Asset Versions
     * List immutable versions of a Project Asset.
     * @param projectId
     * @param assetId
     * @param ws
     * @param molabSession
     * @returns AssetVersionResponse Successful Response
     * @throws ApiError
     */
    public static listProjectAssetVersionsWs(
        projectId: string,
        assetId: string,
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<Array<AssetVersionResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/assets/{asset_id}/versions',
            path: {
                'project_id': projectId,
                'asset_id': assetId,
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
     * Download Project Asset
     * @param projectId
     * @param assetId
     * @param ws
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadProjectAssetWs(
        projectId: string,
        assetId: string,
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/assets/{asset_id}/download',
            path: {
                'project_id': projectId,
                'asset_id': assetId,
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
