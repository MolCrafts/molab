/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { KnowledgeSearchRow } from './KnowledgeSearchRow';
/**
 * ``GET /knowledge/search`` — body-aware retrieval over the documents.
 */
export type KnowledgeSearchResponse = {
    hits: Array<KnowledgeSearchRow>;
    truncated: boolean;
};

