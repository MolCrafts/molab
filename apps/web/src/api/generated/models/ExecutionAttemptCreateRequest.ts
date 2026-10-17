/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Create one physical attempt for an existing logical Run.
 */
export type ExecutionAttemptCreateRequest = {
    mode?: ExecutionAttemptCreateRequest.mode;
    basedOnExecutionId?: (string | null);
    checkpointArtifactId?: (string | null);
    /**
     * Recompute every task, ignoring cached node results. Always true for reproduce.
     */
    bypassCache?: boolean;
    target?: (string | null);
    /**
     * Submit the queued Execution after it is created.
     */
    dispatch?: boolean;
};
export namespace ExecutionAttemptCreateRequest {
    export enum mode {
        INITIAL = 'initial',
        RETRY = 'retry',
        RERUN = 'rerun',
        RESUME = 'resume',
        REPRODUCE = 'reproduce',
    }
}

