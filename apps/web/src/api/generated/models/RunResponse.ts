/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ExecutionResponse } from './ExecutionResponse';
import type { RunStatusSummaryResponse } from './RunStatusSummaryResponse';
import type { WorkflowSnapshotResponse } from './WorkflowSnapshotResponse';
export type RunResponse = {
    id: string;
    name: string;
    path: string;
    projectId: string;
    experimentId: string;
    definitionHash: string;
    experimentRevisionId: string;
    statusSummary: RunStatusSummaryResponse;
    created: string;
    finished?: (string | null);
    parameters?: Record<string, any>;
    workflow?: (WorkflowSnapshotResponse | null);
    workflowSource?: (string | null);
    executions?: Array<ExecutionResponse>;
    target?: (string | null);
    ref: string;
};

