/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Import a file already in the served workspace as a project asset.
 */
export type AssetImportRequest = {
    /**
     * Asset title.
     */
    name: string;
    /**
     * Workspace-relative path of the file.
     */
    path: string;
    /**
     * Semantic type, e.g. chemical/monomer (metadata is checked).
     */
    kind?: (string | null);
    /**
     * Structured metadata.
     */
    metadata?: Record<string, any>;
    action?: AssetImportRequest.action;
};
export namespace AssetImportRequest {
    export enum action {
        COPY = 'copy',
        REFERENCE = 'reference',
    }
}

