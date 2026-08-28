/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AssetResponse } from '../models/AssetResponse';
import type { Body_uploadProjectAsset } from '../models/Body_uploadProjectAsset';
import type { MessageResponse } from '../models/MessageResponse';
import type { ProjectCreateRequest } from '../models/ProjectCreateRequest';
import type { ProjectResponse } from '../models/ProjectResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ProjectsService {
    /**
     * List Projects
     * @param molexpSession
     * @returns ProjectResponse Successful Response
     * @throws ApiError
     */
    public static listProjects(
        molexpSession?: (string | null),
    ): CancelablePromise<Array<ProjectResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects',
            cookies: {
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Project
     * @param requestBody
     * @param molexpSession
     * @returns ProjectResponse Successful Response
     * @throws ApiError
     */
    public static createProject(
        requestBody: ProjectCreateRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<ProjectResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects',
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
     * Delete Project
     * @param projectId
     * @param molexpSession
     * @returns MessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteProject(
        projectId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<MessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/projects/{project_id}',
            path: {
                'project_id': projectId,
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
     * Get Project
     * @param projectId
     * @param molexpSession
     * @returns ProjectResponse Successful Response
     * @throws ApiError
     */
    public static getProject(
        projectId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<ProjectResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}',
            path: {
                'project_id': projectId,
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
     * List Project Assets
     * List every asset (any kind) in the project scope via the catalog.
     * @param projectId
     * @param limit
     * @param molexpSession
     * @returns AssetResponse Successful Response
     * @throws ApiError
     */
    public static listProjectAssets(
        projectId: string,
        limit: number = 100,
        molexpSession?: (string | null),
    ): CancelablePromise<Array<AssetResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/assets',
            path: {
                'project_id': projectId,
            },
            cookies: {
                'molexp_session': molexpSession,
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
     * Upload Project Asset
     * Upload a file into the project's ``DataAssetLibrary``.
     * @param projectId
     * @param formData
     * @param molexpSession
     * @returns AssetResponse Successful Response
     * @throws ApiError
     */
    public static uploadProjectAsset(
        projectId: string,
        formData: Body_uploadProjectAsset,
        molexpSession?: (string | null),
    ): CancelablePromise<AssetResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/assets/upload',
            path: {
                'project_id': projectId,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Project Asset
     * @param projectId
     * @param assetId
     * @param molexpSession
     * @returns AssetResponse Successful Response
     * @throws ApiError
     */
    public static getProjectAsset(
        projectId: string,
        assetId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<AssetResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/assets/{asset_id}',
            path: {
                'project_id': projectId,
                'asset_id': assetId,
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
     * Download Project Asset
     * @param projectId
     * @param assetId
     * @param molexpSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadProjectAsset(
        projectId: string,
        assetId: string,
        molexpSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/assets/{asset_id}/download',
            path: {
                'project_id': projectId,
                'asset_id': assetId,
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
     * List Projects
     * @param ws
     * @param molexpSession
     * @returns ProjectResponse Successful Response
     * @throws ApiError
     */
    public static listProjects1(
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<Array<ProjectResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects',
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
     * Create Project
     * @param ws
     * @param requestBody
     * @param molexpSession
     * @returns ProjectResponse Successful Response
     * @throws ApiError
     */
    public static createProject1(
        ws: string,
        requestBody: ProjectCreateRequest,
        molexpSession?: (string | null),
    ): CancelablePromise<ProjectResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects',
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
     * Delete Project
     * @param projectId
     * @param ws
     * @param molexpSession
     * @returns MessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteProject1(
        projectId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<MessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/workspaces/{ws}/projects/{project_id}',
            path: {
                'project_id': projectId,
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
     * Get Project
     * @param projectId
     * @param ws
     * @param molexpSession
     * @returns ProjectResponse Successful Response
     * @throws ApiError
     */
    public static getProject1(
        projectId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<ProjectResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}',
            path: {
                'project_id': projectId,
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
     * List Project Assets
     * List every asset (any kind) in the project scope via the catalog.
     * @param projectId
     * @param ws
     * @param limit
     * @param molexpSession
     * @returns AssetResponse Successful Response
     * @throws ApiError
     */
    public static listProjectAssets1(
        projectId: string,
        ws: string,
        limit: number = 100,
        molexpSession?: (string | null),
    ): CancelablePromise<Array<AssetResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/assets',
            path: {
                'project_id': projectId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
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
     * Upload Project Asset
     * Upload a file into the project's ``DataAssetLibrary``.
     * @param projectId
     * @param ws
     * @param formData
     * @param molexpSession
     * @returns AssetResponse Successful Response
     * @throws ApiError
     */
    public static uploadProjectAsset1(
        projectId: string,
        ws: string,
        formData: Body_uploadProjectAsset,
        molexpSession?: (string | null),
    ): CancelablePromise<AssetResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/workspaces/{ws}/projects/{project_id}/assets/upload',
            path: {
                'project_id': projectId,
                'ws': ws,
            },
            cookies: {
                'molexp_session': molexpSession,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
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
     * @param molexpSession
     * @returns AssetResponse Successful Response
     * @throws ApiError
     */
    public static getProjectAsset1(
        projectId: string,
        assetId: string,
        ws: string,
        molexpSession?: (string | null),
    ): CancelablePromise<AssetResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/assets/{asset_id}',
            path: {
                'project_id': projectId,
                'asset_id': assetId,
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
     * Download Project Asset
     * @param projectId
     * @param assetId
     * @param ws
     * @param molexpSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadProjectAsset1(
        projectId: string,
        assetId: string,
        ws: string,
        molexpSession?: (string | null),
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
                'molexp_session': molexpSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
