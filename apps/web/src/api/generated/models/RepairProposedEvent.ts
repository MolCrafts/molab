/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Emitted when the repair loop proposes a plan diff.
 */
export type RepairProposedEvent = {
    timestamp?: string;
    kind?: string;
    failed_invariant: string;
    rationale?: string;
};

