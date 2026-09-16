/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One registered OKF knowledge base (a group wiki).
 *
 * Named "knowledge base", not "knowledge source": ``agent_admin`` already owns
 * ``KnowledgeSourcesResponse`` for the molmcp *package* allowlist, an unrelated
 * concept. Two schemas with one name collide in the generated OpenAPI client,
 * and the ambiguity was real before it was mechanical.
 */
export type KnowledgeBaseRow = {
    available: boolean;
    description?: string;
    name: string;
    root: string;
    scope: string;
};

