/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Wire form for a :class:`WorkspaceTarget`.
 */
export type WorkspaceTargetResponse = {
    cacheDir?: (string | null);
    cacheTtlSeconds?: number;
    host: string;
    identityFile?: (string | null);
    name: string;
    port?: (number | null);
    rootPath: string;
    sshOpts?: Array<string>;
};

