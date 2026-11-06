/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type RunCreateRequest = {
    /**
     * Run params
     */
    params?: Record<string, any>;
    /**
     * Asset ids this run consumes. Bound into the root task as paths.
     */
    inputs?: Array<string>;
    /**
     * Declared compute-target hint (must exist in workspace registry)
     */
    target?: (string | null);
};

