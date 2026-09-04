/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Partial update of a note's ``meta.json`` tags/status.
 *
 * Each field is independently optional; ``None`` means "leave untouched", which
 * maps onto ``Note.set_tags`` / ``Note.set_status`` each preserving the sibling
 * field. A request with both ``None`` is a no-op that returns the current summary.
 */
export type DocMetaUpdate = {
    tags?: (Array<string> | null);
    status?: (string | null);
};

