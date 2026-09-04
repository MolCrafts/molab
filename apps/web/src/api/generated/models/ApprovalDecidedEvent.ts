/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Emitted with the verdict once an approval gate resolves.
 */
export type ApprovalDecidedEvent = {
    timestamp?: string;
    kind?: string;
    gate: string;
    approved: boolean;
    reason?: string;
};

