/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { KnowledgeGraphEdge } from './KnowledgeGraphEdge';
import type { NoteSummary } from './NoteSummary';
/**
 * ``GET /knowledge/graph`` — every listed document and every typed link between them.
 */
export type KnowledgeGraphResponse = {
    nodes: Array<NoteSummary>;
    edges: Array<KnowledgeGraphEdge>;
};
