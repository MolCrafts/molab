/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WorkspaceInfoResponse = {
    assetCount: number;
    connected?: (boolean | null);
    indexed?: (boolean | null);
    projectCount: number;
    ready?: (boolean | null);
    root: string;
    versions?: Record<string, number>;
    warnings?: Array<string>;
};

