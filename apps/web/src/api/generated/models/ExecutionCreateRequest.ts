/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ExecutionCreateRequest = {
    /**
     * Target experiment ID
     */
    experimentId: string;
    /**
     * Run params ('parameters' accepted as a deprecated alias)
     */
    params?: Record<string, any>;
    /**
     * Target project ID
     */
    projectId: string;
    /**
     * Optional workflow IR (matches schema/workflow.json). When provided and the experiment has no workflow bound yet, the server binds it and persists the IR to disk. Subsequent calls reuse the on-disk binding.
     */
    workflowJson?: (Record<string, any> | null);
};

