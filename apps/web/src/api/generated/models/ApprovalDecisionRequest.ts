/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Operator decision — ReviewDecision-shaped wire body.
 *
 * ``action`` is required (approve|reject|revise).
 */
export type ApprovalDecisionRequest = {
    action: ApprovalDecisionRequest.action;
    edits?: (Record<string, any> | null);
    fieldValues?: Record<string, any>;
    reason?: (string | null);
    requestId: string;
};
export namespace ApprovalDecisionRequest {
    export enum action {
        APPROVE = 'approve',
        REJECT = 'reject',
        REVISE = 'revise',
    }
}

