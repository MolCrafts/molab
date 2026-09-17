/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One execution attempt of a Run.
 *
 * Mirrors :class:`molab.workspace.models.ExecutionRecord` with
 * JSON-friendly field names so the UI can render a per-attempt
 * timeline.
 */
export type ExecutionResponse = {
    id: string;
    runId: string;
    mode: string;
    status: string;
    createdAt: string;
    startedAt?: (string | null);
    finishedAt?: (string | null);
    basedOnExecutionId?: (string | null);
    checkpointArtifactId?: (string | null);
    executor?: Record<string, any>;
    environment?: Record<string, any>;
    artifactIds?: Array<string>;
    error?: (Record<string, any> | null);
};

