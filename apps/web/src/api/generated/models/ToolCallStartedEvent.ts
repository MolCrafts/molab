/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Emitted when the emergent loop dispatches a tool call.
 *
 * ``args_summary`` is a short human-readable rendering of the call
 * arguments — never the full payload, so the event stream stays cheap.
 */
export type ToolCallStartedEvent = {
    timestamp?: string;
    kind?: string;
    tool_name: string;
    args_summary?: string;
};

