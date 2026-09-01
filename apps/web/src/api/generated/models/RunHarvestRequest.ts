/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Harvest a terminal run into a sourced KnowledgeItem under its experiment.
 */
export type RunHarvestRequest = {
    /**
     * Author string
     */
    createdBy?: string;
    /**
     * Knowledge class name
     */
    kind: RunHarvestRequest.kind;
    /**
     * Optional KnowledgeItem name
     */
    name?: (string | null);
    /**
     * Non-empty interpretation
     */
    narrative: string;
    /**
     * Optional headline results table
     */
    results?: (Record<string, any> | null);
};
export namespace RunHarvestRequest {
    /**
     * Knowledge class name
     */
    export enum kind {
        OBSERVATION = 'Observation',
        DECISION = 'Decision',
        ASSUMPTION = 'Assumption',
        CONSTRAINT = 'Constraint',
        FINDING = 'Finding',
        FAILURE_ANALYSIS = 'FailureAnalysis',
        PROTOCOL_NOTE = 'ProtocolNote',
        PARAMETER_RATIONALE = 'ParameterRationale',
        OPEN_QUESTION = 'OpenQuestion',
        PLAN = 'Plan',
    }
}

