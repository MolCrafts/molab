/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Wire form for a :class:`WorkspaceTarget`.
 */
export type WorkspaceTargetResponse = {
    name: string;
    host: string;
    rootPath: string;
    port?: (number | null);
    identityFile?: (string | null);
    sshOpts?: Array<string>;
    cacheDir?: (string | null);
    cacheTtlSeconds?: number;
};

