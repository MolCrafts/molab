/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { KnowledgeSearchRow } from './KnowledgeSearchRow';
/**
 * ``GET /knowledge/search`` — ranked retrieval across the knowledge bases.
 */
export type KnowledgeSearchResponse = {
    hits: Array<KnowledgeSearchRow>;
    truncated: boolean;
};

