/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Harvest a terminal run into sourced Knowledge under its experiment.
 */
export type RunHarvestRequest = {
    /**
     * Knowledge class name
     */
    cls?: RunHarvestRequest.cls;
    /**
     * Non-empty interpretation
     */
    narrative: string;
    /**
     * Author string
     */
    createdBy?: string;
    /**
     * Optional knowledge document name
     */
    name?: (string | null);
    /**
     * Optional headline results table
     */
    results?: (Record<string, any> | null);
};
export namespace RunHarvestRequest {
    /**
     * Knowledge class name
     */
    export enum cls {
        NOTE = 'Note',
        LITERATURE = 'Literature',
        REPORT = 'Report',
        FINDING = 'Finding',
        PLAN = 'Plan',
        OBSERVATION = 'Observation',
    }
}

