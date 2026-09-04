/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ExecutionCreateRequest = {
    /**
     * Target project ID
     */
    projectId: string;
    /**
     * Target experiment ID
     */
    experimentId: string;
    /**
     * Run params ('parameters' accepted as a deprecated alias)
     */
    params?: Record<string, any>;
    /**
     * Optional workflow IR (matches schema/workflow.json). When provided and the experiment has no workflow bound yet, the server binds it and persists the IR to disk. Subsequent calls reuse the on-disk binding.
     */
    workflowJson?: (Record<string, any> | null);
};

