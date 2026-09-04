/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ExecutionRecordResponse } from './ExecutionRecordResponse';
import type { RunStatusSummaryResponse } from './RunStatusSummaryResponse';
import type { WorkflowSnapshotResponse } from './WorkflowSnapshotResponse';
export type RunResponse = {
    id: string;
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
    executions?: Array<ExecutionRecordResponse>;
    target?: (string | null);
};

