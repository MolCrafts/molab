/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AgentRef } from './AgentRef';
import type { JSONValue } from './JSONValue';
/**
 * One dated, evidence-backed step; details are recorded facts, not inferred intent.
 */
export type ReplayEvent = {
    id: string;
    at: string;
    kind: ReplayEvent.kind;
    action: string;
    title: string;
    ref?: (string | null);
    actor?: (AgentRef | null);
    commit?: (string | null);
    document?: (string | null);
    details?: Record<string, JSONValue>;
};
export namespace ReplayEvent {
    export enum kind {
        EXPERIMENT = 'experiment',
        RUN = 'run',
        EXECUTION = 'execution',
        KNOWLEDGE = 'knowledge',
        ASSET = 'asset',
        HISTORY = 'history',
    }
}
