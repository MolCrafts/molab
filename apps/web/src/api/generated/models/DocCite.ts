/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One edge a new document carries from the moment it lands.
 */
export type DocCite = {
    /**
     * A workspace-relative knowledge document path or an entity ref.
     */
    target: string;
    role?: DocCite.role;
};
export namespace DocCite {
    export enum role {
        DERIVED_FROM = 'derived_from',
        CITES = 'cites',
        SUPPORTS = 'supports',
        CONTRADICTS = 'contradicts',
        REFERENCES = 'references',
    }
}

