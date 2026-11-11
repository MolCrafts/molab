/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One workspace root and its molq destination identity.
 */
export type WorkspaceTargetCreateRequest = {
    name: string;
    registryId: string;
    clusterId: string;
    rootPath: string;
    cacheDir?: (string | null);
    cacheMode?: WorkspaceTargetCreateRequest.cacheMode;
};
export namespace WorkspaceTargetCreateRequest {
    export enum cacheMode {
        PINNED = 'pinned',
        STRICT = 'strict',
    }
}

