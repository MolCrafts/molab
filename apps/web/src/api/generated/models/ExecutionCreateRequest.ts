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
     * Optional workflow IR (WorkflowCodec.ir_to_spec). On an unbound experiment it is bound as the document kind before the run is created. On a document experiment it must match the bound document. On a code experiment it is rejected; convert with PUT .../workflow and convertToDocument. The request never writes the in-process binding memo.
     */
    workflowJson?: (Record<string, any> | null);
};

