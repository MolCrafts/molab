/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Replace a document's own fields whole; an omitted key is removed.
 *
 * ``ifMatch`` is the digest the caller read; a changed file answers 409.
 * ``body`` optionally rewrites the narrative in the same write.
 */
export type DocFieldsUpdate = {
    fields: Record<string, any>;
    ifMatch?: (string | null);
    body?: (string | null);
};

