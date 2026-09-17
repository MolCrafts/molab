/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Payload for ``POST /api/workspace/targets``.
 */
export type WorkspaceTargetCreateRequest = {
    /**
     * Unique slug-shaped identifier
     */
    name: string;
    /**
     * ``user@host`` or bare hostname for SSH
     */
    host: string;
    /**
     * Absolute POSIX path on the remote host
     */
    rootPath: string;
    /**
     * SSH port
     */
    port?: (number | null);
    /**
     * Absolute path to an SSH identity file
     */
    identityFile?: (string | null);
    /**
     * Extra ``ssh`` argv tokens
     */
    sshOpts?: Array<string>;
    /**
     * Override local mirror root (defaults to ~/.molab/remote_cache/<name>)
     */
    cacheDir?: (string | null);
    /**
     * Mirror pin policy: >0 pin until user refresh; 0 = re-stat remote on every read
     */
    cacheTtlSeconds?: number;
};

