/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One narrative occurrence; its id is valid only with this file digest.
 */
export type DocRelation = {
    id: number;
    target: string;
    role: DocRelation.role;
    label: string;
    kind: DocRelation.kind;
};
export namespace DocRelation {
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
