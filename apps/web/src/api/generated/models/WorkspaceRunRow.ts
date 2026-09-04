/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JSONValue } from './JSONValue';
import type { RunStatusSummaryResponse } from './RunStatusSummaryResponse';
import type { WorkspaceExecutionRow } from './WorkspaceExecutionRow';
/**
 * Logical Run definition plus a derived summary of its Executions.
 */
export type WorkspaceRunRow = {
    id: string;
    name: string;
    projectId: string;
    projectName: string;
    experimentId: string;
    experimentName: string;
    definitionHash: string;
    experimentRevisionId: string;
    inputAssetIds?: Array<string>;
    targetHint?: (string | null);
    statusSummary: RunStatusSummaryResponse;
    parameters?: Record<string, JSONValue>;
    createdAt: string;
    executions?: Array<WorkspaceExecutionRow>;
};

