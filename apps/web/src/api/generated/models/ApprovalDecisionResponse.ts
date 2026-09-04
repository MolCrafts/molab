/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Post-decision task summary.
 */
export type ApprovalDecisionResponse = {
    taskKind: ApprovalDecisionResponse.taskKind;
    taskId: string;
    status: string;
};
export namespace ApprovalDecisionResponse {
    export enum taskKind {
        PLAN = 'plan',
        CURATE = 'curate',
    }
}

