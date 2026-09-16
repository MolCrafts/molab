/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One ranked search hit projected from the bundle index entry.
 */
export type KnowledgeSearchRow = {
    path: string;
    ref?: string;
    score?: number;
    snippet?: (string | null);
    source?: string;
    tags?: Array<string>;
    title: string;
    type: string;
};

