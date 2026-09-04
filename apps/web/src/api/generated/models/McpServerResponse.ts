/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One MCP server row (no secret values — names/refs only).
 */
export type McpServerResponse = {
    name: string;
    scope: string;
    transport: string;
    command: (string | null);
    args: Array<string>;
    url: (string | null);
    envKeys: Array<string>;
    env?: Record<string, string>;
    headerKeys: Array<string>;
    secretRefs: Array<string>;
    unresolvedSecrets: Array<string>;
    shadowed: boolean;
    valid: boolean;
    invalidReason: string;
    auth?: (Record<string, any> | null);
    knowledgeSources?: Array<string>;
};

