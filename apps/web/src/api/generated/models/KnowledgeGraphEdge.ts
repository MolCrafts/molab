/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One typed link from a document's narrative.
 */
export type KnowledgeGraphEdge = {
    /**
     * `relPath` of the document holding the link.
     */
    source: string;
    /**
     * `relPath` of the linked document (`document`), the path the link names relative to the served root (`missing`), the reference verbatim (`ref`), or the URL verbatim (`external`).
     */
    target: string;
    role: KnowledgeGraphEdge.role;
    kind: KnowledgeGraphEdge.kind;
};
export namespace KnowledgeGraphEdge {
    export enum role {
        DERIVED_FROM = 'derived_from',
        CITES = 'cites',
        SUPERSEDES = 'supersedes',
        SUPPORTS = 'supports',
        CONTRADICTS = 'contradicts',
        RECORDS = 'records',
        REFERENCES = 'references',
    }
    export enum kind {
        DOCUMENT = 'document',
        REF = 'ref',
        EXTERNAL = 'external',
        MISSING = 'missing',
    }
}
