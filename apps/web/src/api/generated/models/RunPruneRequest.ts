/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Select attempts to prune. ``apply`` false returns the plan and deletes nothing.
 */
export type RunPruneRequest = {
    executionIds?: (Array<string> | null);
    statuses?: (Array<string> | null);
    apply?: boolean;
};

