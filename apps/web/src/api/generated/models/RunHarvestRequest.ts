/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Harvest a terminal run into a sourced KnowledgeItem under its experiment.
 */
export type RunHarvestRequest = {
    /**
     * Knowledge class name
     */
    kind: RunHarvestRequest.kind;
    /**
     * Non-empty interpretation
     */
    narrative: string;
    /**
     * Author string
     */
    createdBy?: string;
    /**
     * Optional KnowledgeItem name
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

