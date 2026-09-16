/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Runtime workflow graph state read from ``workflow.json``.
 *
 * The document grows with node count *and* with the size of each node's
 * persisted outputs, so it is served in three bands: inline below
 * ``EXECUTION_JSON_INLINE_BYTES``; summarised below
 * ``EXECUTION_JSON_MAX_BYTES`` (per-node status/snapshot/timestamps kept,
 * the bulky ``outputs`` dropped) with ``workflowTruncated`` set; and
 * refused with 413 above it.  ``workflowBytes`` is the document's real size
 * either way.
 */
export type RunExecutionResponse = {
    execution_id?: (string | null);
    status?: string;
    workflow?: (Record<string, any> | null);
    workflowBytes?: (number | null);
    workflowTruncated?: boolean;
};

