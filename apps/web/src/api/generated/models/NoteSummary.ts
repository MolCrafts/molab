/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type NoteSummary = {
    name: string;
    relPath: string;
    hostPath?: string;
    excerpt: string;
    tags?: Array<string>;
    status?: (string | null);
    cls?: string;
    format?: NoteSummary.format;
    /**
     * ISO-8601 UTC time the file was last modified.
     */
    updatedAt?: (string | null);
    /**
     * ISO-8601 UTC creation stamp (`created_at`); absent on older documents.
     */
    createdAt?: (string | null);
};
export namespace NoteSummary {
    export enum format {
        MD = 'md',
        HTML = 'html',
        TEX = 'tex',
    }
}

