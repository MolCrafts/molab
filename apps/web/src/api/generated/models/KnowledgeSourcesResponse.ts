/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Package scope for the **molmcp** MCP server entry (not a global agent key).
 *
 * Stored as ``env.MOLMCP_SOURCES`` on that server's config row. Plan sessions
 * and capability grounding read the same pin from the MCP store.
 */
export type KnowledgeSourcesResponse = {
    sources?: Array<string>;
    knownPackages?: Array<string>;
    unrestricted?: boolean;
    serverName?: string;
    scope?: string;
    configured?: boolean;
};

