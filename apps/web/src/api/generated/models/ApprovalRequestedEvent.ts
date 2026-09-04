/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Emitted when the harness opens an approval gate for a reviewer.
 */
export type ApprovalRequestedEvent = {
    timestamp?: string;
    kind?: string;
    gate: string;
    summary?: string;
};

