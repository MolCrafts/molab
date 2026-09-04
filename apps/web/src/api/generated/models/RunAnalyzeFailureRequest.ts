/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Analyze a failed run into a sourced FailureAnalysis KnowledgeItem.
 */
export type RunAnalyzeFailureRequest = {
    /**
     * Optional interpretation; when omitted a deterministic template is used
     */
    narrative?: (string | null);
    /**
     * Author string
     */
    createdBy?: string;
    /**
     * When true, also accept cancelled runs (default: failed only)
     */
    force?: boolean;
    /**
     * Optional KnowledgeItem name
     */
    name?: (string | null);
};

