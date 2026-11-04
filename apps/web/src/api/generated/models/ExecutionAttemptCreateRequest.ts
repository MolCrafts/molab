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
    /**
     * Idempotency key. When an attempt of this Run was already created with the same key, that attempt is returned and nothing new is created or dispatched, so a caller that lost the response can retry safely.
     */
    requestKey?: (string | null);
    /**
     * Software agent recorded as the attempt's creator (default: the UI).
     */
    requestedBy?: (string | null);
};
export namespace ExecutionAttemptCreateRequest {
    export enum mode {
        INITIAL = 'initial',
        RERUN = 'rerun',
        RESUME = 'resume',
        REPRODUCE = 'reproduce',
    }
}

