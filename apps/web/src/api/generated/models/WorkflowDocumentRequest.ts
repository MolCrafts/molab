/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Edited workflow IR document posted by the free-layout canvas.
 *
 * ``document`` is the identity-free wire IR (``{task_configs, links, entries,
 * loops, parallels, ...}``). The route validates it through
 * ``WorkflowCodec.ir_to_spec`` before persisting. The compiled digest lives
 * on the Execution, not in this document.
 */
export type WorkflowDocumentRequest = {
    /**
     * Workflow IR document
     */
    document: Record<string, any>;
    /**
     * Replace a code-kind binding with this document
     */
    convertToDocument?: boolean;
};

