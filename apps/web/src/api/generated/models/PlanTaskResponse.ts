/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One background plan task's current state (UI polls this).
 */
export type PlanTaskResponse = {
    taskId: string;
    runId: string;
    projectId: string;
    experimentId: string;
    status: string;
    createdAt: string;
    model: string;
    draftPreview: string;
    workflowPersisted?: boolean;
    execute?: boolean;
    error?: (string | null);
    recordErrors?: Array<string>;
};

