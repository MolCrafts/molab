/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One physical attempt that realizes a logical Run.
 */
export type WorkspaceExecutionRow = {
    executionId: string;
    runId: string;
    mode: string;
    status: string;
    createdAt: string;
    startedAt?: (string | null);
    finishedAt?: (string | null);
    durationSeconds?: (number | null);
    basedOnExecutionId?: (string | null);
    checkpointArtifactId?: (string | null);
    schedulerJobId?: (string | null);
    backend?: (string | null);
    backendMetadata?: Record<string, string>;
};

