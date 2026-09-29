/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One Execution's node journal as the workflow layer reports it (``molab.workflow.read_journal``).
 *
 * ``status`` is the Execution record's status; ``workflow`` is the journal
 * document (header + ``task_configs``), or null before the journal exists.
 */
export type RunExecutionResponse = {
    executionId?: (string | null);
    status?: string;
    workflow?: (Record<string, any> | null);
};

