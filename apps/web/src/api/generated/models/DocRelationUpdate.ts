/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DocRelationUpdate = {
    action: DocRelationUpdate.action;
    ifMatch: string;
    id?: (number | null);
    target?: (string | null);
    role?: DocRelationUpdate.role;
    text?: (string | null);
};
export namespace DocRelationUpdate {
    export enum action {
        ADD = 'add',
        REPLACE = 'replace',
        REMOVE = 'remove',
    }
    export enum role {
        DERIVED_FROM = 'derived_from',
        CITES = 'cites',
        SUPERSEDES = 'supersedes',
        SUPPORTS = 'supports',
        CONTRADICTS = 'contradicts',
        RECORDS = 'records',
        REFERENCES = 'references',
    }
}
