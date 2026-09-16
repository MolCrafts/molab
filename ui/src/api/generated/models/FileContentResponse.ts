/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * A bounded UTF-8 window over a workspace file.
 *
 * ``content`` is the ``[offset, end)`` slice of a ``totalBytes`` file.  A
 * file larger than the window used to be refused with 413; it is now served
 * windowed, because a user opening a 500 MB log wants to see *something*
 * and a viewer can page with ``since_offset=end``.
 */
export type FileContentResponse = {
    content: string;
    end?: number;
    offset?: number;
    totalBytes?: number;
    truncated?: boolean;
};

