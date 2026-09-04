/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HealthResponse = {
    status: string;
    workspaceAvailable: boolean;
    capabilities?: Record<string, boolean>;
    /**
     * True when the server process has auth enabled (UI should gate on login).
     */
    authRequired?: boolean;
};

