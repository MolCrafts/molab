/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * The persisted (normalized) workflow IR document for an experiment.
 */
export type WorkflowDocumentResponse = {
    /**
     * Normalized workflow IR document
     */
    document: Record<string, any>;
    /**
     * Owning experiment id
     */
    experimentId: string;
    /**
     * Owning project id
     */
    projectId: string;
};

