/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagedAssetResponse } from '../models/ManagedAssetResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AssetsService {
    /**
     * Get Asset
     * Read an asset by canonical id, across scopes inside the served boundary.
     * @param assetId
     * @param molabSession
     * @returns ManagedAssetResponse Successful Response
     * @throws ApiError
     */
    public static getAsset(
        assetId: string,
        molabSession?: (string | null),
    ): CancelablePromise<ManagedAssetResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/assets/{asset_id}',
            path: {
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
     * Download Asset
     * Stream verified asset bytes through their owning scope's repository.
     * @param assetId
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadAsset(
        assetId: string,
        molabSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/assets/{asset_id}/download',
            path: {
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
     * Preview Asset
     * Render a preview of a sidecar-backed dataset asset.
     *
     * Args:
     * asset_id: Catalog id of the dataset asset.
     * format: ``frames`` (extended-XYZ bytes for the JS trajectory viewer)
     * or ``png`` (headless molvis snapshot).
     * limit: Host-owned cap on the number of frames previewed.
     *
     * Returns:
     * A streaming response — ``chemical/x-xyz`` for ``frames``,
     * ``image/png`` for ``png``.
     *
     * Raises:
     * AssetNotFoundError: The asset resolved, but its payload is missing (404).
     * PreviewSidecarNotFoundError: No sidecar next to the dataset (404).
     * NoReaderInSidecarError / PreviewReaderError: The sidecar names no
     * reader, or reading through it failed (422).
     * @param assetId
     * @param format
     * @param limit
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static previewAsset(
        assetId: string,
        format: 'frames' | 'png' = 'frames',
        limit: number = 200,
        molabSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/assets/{asset_id}/preview',
            path: {
                'asset_id': assetId,
            },
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'format': format,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Asset
     * Read an asset by canonical id, across scopes inside the served boundary.
     * @param assetId
     * @param ws
     * @param molabSession
     * @returns ManagedAssetResponse Successful Response
     * @throws ApiError
     */
    public static getAssetWs(
        assetId: string,
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<ManagedAssetResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/assets/{asset_id}',
            path: {
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
     * Download Asset
     * Stream verified asset bytes through their owning scope's repository.
     * @param assetId
     * @param ws
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadAssetWs(
        assetId: string,
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/assets/{asset_id}/download',
            path: {
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
     * Preview Asset
     * Render a preview of a sidecar-backed dataset asset.
     *
     * Args:
     * asset_id: Catalog id of the dataset asset.
     * format: ``frames`` (extended-XYZ bytes for the JS trajectory viewer)
     * or ``png`` (headless molvis snapshot).
     * limit: Host-owned cap on the number of frames previewed.
     *
     * Returns:
     * A streaming response — ``chemical/x-xyz`` for ``frames``,
     * ``image/png`` for ``png``.
     *
     * Raises:
     * AssetNotFoundError: The asset resolved, but its payload is missing (404).
     * PreviewSidecarNotFoundError: No sidecar next to the dataset (404).
     * NoReaderInSidecarError / PreviewReaderError: The sidecar names no
     * reader, or reading through it failed (422).
     * @param assetId
     * @param ws
     * @param format
     * @param limit
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static previewAssetWs(
        assetId: string,
        ws: string,
        format: 'frames' | 'png' = 'frames',
        limit: number = 200,
        molabSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/assets/{asset_id}/preview',
            path: {
                'asset_id': assetId,
                'ws': ws,
            },
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'format': format,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
