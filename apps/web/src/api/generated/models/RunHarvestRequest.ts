/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Harvest a terminal run into sourced Knowledge under its experiment.
 */
export type RunHarvestRequest = {
    /**
     * The class to harvest into.
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
     * Values to pin as spans on assets this run registered
     */
    results?: (Record<string, any> | null);
};
export namespace RunHarvestRequest {
    /**
     * The class to harvest into.
     */
    export enum cls {
        FINDING = 'Finding',
        OBSERVATION = 'Observation',
        REPORT = 'Report',
    }
}

