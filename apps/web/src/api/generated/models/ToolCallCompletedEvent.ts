/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Emitted when a dispatched tool call returns.
 *
 * ``ok`` is ``False`` when the tool raised / returned a retry prompt;
 * ``result_summary`` is a short rendering of the return value.
 * ``artifacts`` is the full embed list (plot / structure / table) for the UI.
 */
export type ToolCallCompletedEvent = {
    timestamp?: string;
    kind?: string;
    tool_name: string;
    result_summary?: string;
    ok?: boolean;
    artifacts?: Array<Record<string, any>>;
};

