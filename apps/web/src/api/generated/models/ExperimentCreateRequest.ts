/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ExperimentCreateRequest = {
    /**
     * Human-readable experiment name
     */
    name: string;
    /**
     * Workflow IR document; bound as the document kind
     */
    workflowSource?: (Record<string, any> | null);
    /**
     * Experiment description
     */
    description?: string;
    /**
     * Parameter space definition
     */
    parameterSpace?: Record<string, any>;
    /**
     * Compute target name new runs should default to (must exist)
     */
    defaultTarget?: (string | null);
};

