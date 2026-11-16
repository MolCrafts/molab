/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WorkspaceTargetResponse = {
    name: string;
    registryId: string;
    clusterId: string;
    rootPath: string;
    cacheDir?: (string | null);
    cacheMode?: WorkspaceTargetResponse.cacheMode;
};
export namespace WorkspaceTargetResponse {
    export enum cacheMode {
        PINNED = 'pinned',
        STRICT = 'strict',
    }
}

