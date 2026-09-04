/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One pending request awaiting an operator decision.
 *
 * ``taskId`` is the **single public handle** shared with the Agents hub
 * (agent-task id / plan conversation id). Decide routes resolve the live
 * runtime task by this same id — never a second parallel plan-* registry
 * id that the UI cannot navigate to.
 */
export type PendingApprovalItem = {
    taskKind: PendingApprovalItem.taskKind;
    taskId: string;
    runId: string;
    projectId: string;
    experimentId: string;
    requestId: string;
    intent: string;
    reason: string;
    metadata?: Record<string, any>;
    requestedAt: string;
    preview?: string;
    packId?: (string | null);
    formDocument?: (Record<string, any> | null);
    scope?: string;
    targetAgentId?: (string | null);
};
export namespace PendingApprovalItem {
    export enum taskKind {
        PLAN = 'plan',
        CURATE = 'curate',
    }
}

