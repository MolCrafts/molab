/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Result of a bounded authentication attempt.
 */
export type WorkspaceConnectResponse = {
    ok: boolean;
    key: string;
    destination: string;
    authenticated: boolean;
    message?: string;
};

