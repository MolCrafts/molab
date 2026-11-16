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
    /**
     * Recompute every task, ignoring cached node results. Always true for reproduce.
     */
    bypassCache?: boolean;
    /**
     * Compute target the attempt is submitted to; the built-in ``local`` target runs it on this machine. Every created attempt is submitted — an attempt nothing will run is never created.
     */
    target?: string;
    /**
     * Idempotency key. When an attempt of this Run was already created with the same key, that attempt is returned and nothing new is created or dispatched, so a caller that lost the response can retry safely.
     */
    requestKey?: (string | null);
    /**
     * Software agent recorded as the attempt's creator (default: the UI).
     */
    requestedBy?: (string | null);
    /**
     * Rerun only these tasks (``mode`` must be ``rerun``): each executes with the inputs the predecessor attempt recorded, every other completed task is seeded from its record, and every task downstream of a selected one is skipped. Omit to rerun every task.
     */
    tasks?: (Array<string> | null);
    /**
     * How the attempt's task bodies run: worker threads (default), worker processes, or inline on the engine thread. Overrides the workflow's and each task's choice.
     */
    taskExecutor?: ('thread' | 'process' | 'inline' | null);
    /**
     * Worker threads / processes at most.
     */
    maxWorkers?: (number | null);
};
export namespace ExecutionAttemptCreateRequest {
    export enum mode {
        INITIAL = 'initial',
        RERUN = 'rerun',
        RESUME = 'resume',
        REPRODUCE = 'reproduce',
    }
}

