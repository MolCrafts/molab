/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One background curate task's current state (UI polls this).
 */
export type CurateTaskResponse = {
    taskId: string;
    runId: string;
    projectId: string;
    experimentId: string;
    status: string;
    createdAt: string;
    model: string;
    requestPreview: string;
    capabilityId?: (string | null);
    mutationSummary?: (string | null);
    granted?: (boolean | null);
    error?: (string | null);
};

