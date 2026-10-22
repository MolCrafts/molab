/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Execution aggregates for the complete (unpaginated) Run result set.
 */
export type WorkspaceRunsStats = {
    totalRuns?: number;
    totalExecutions?: number;
    activeExecutions?: number;
    byStatus?: Record<string, number>;
};

