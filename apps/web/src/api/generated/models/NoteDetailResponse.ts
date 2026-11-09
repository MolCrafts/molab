/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EntityCard } from './EntityCard';
export type NoteDetailResponse = {
    name: string;
    relPath: string;
    body: string;
    links: Array<string>;
    cards?: Array<EntityCard>;
    record?: Record<string, any>;
    format?: NoteDetailResponse.format;
    /**
     * ISO-8601 UTC time the file was last modified.
     */
    updatedAt?: (string | null);
    /**
     * ISO-8601 UTC creation stamp (`created_at`); absent on older documents.
     */
    createdAt?: (string | null);
};
export namespace NoteDetailResponse {
    export enum format {
        MD = 'md',
        HTML = 'html',
        TEX = 'tex',
    }
}

