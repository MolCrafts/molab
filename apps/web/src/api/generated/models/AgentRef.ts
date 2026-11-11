/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Person, software, workflow, or executor responsible for a fact.
 */
export type AgentRef = {
    id: string;
    type: AgentRef.type;
    name?: (string | null);
};
export namespace AgentRef {
    export enum type {
        PERSON = 'person',
        SOFTWARE = 'software',
        WORKFLOW = 'workflow',
        EXECUTOR = 'executor',
        SYSTEM = 'system',
    }
}
