/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Emitted after the harness compacts the session entry tree.
 */
export type CompactionPerformedEvent = {
    timestamp?: string;
    kind?: string;
    summary: string;
    tokens_before: number;
    entries_summarized: number;
};

