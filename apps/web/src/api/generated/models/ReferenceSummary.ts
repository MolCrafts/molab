/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * A Literature row: its identity and its bibliographic fields.
 */
export type ReferenceSummary = {
    title?: (string | null);
    authors?: Array<string>;
    year?: (number | null);
    doi?: (string | null);
    venue?: (string | null);
    url?: (string | null);
    pdf_path?: (string | null);
    pdf_asset_id?: (string | null);
    source?: string;
    source_key?: (string | null);
    name: string;
    relPath: string;
};

