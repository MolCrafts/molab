/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AgentRef } from './AgentRef';
/**
 * One numbered version of a knowledge file: ``v1`` is its first commit.
 */
export type DocumentVersion = {
    commit: string;
    path: string;
    occurred_at: string;
    summary: string;
    event?: (string | null);
    agent?: (AgentRef | null);
    number: number;
};

