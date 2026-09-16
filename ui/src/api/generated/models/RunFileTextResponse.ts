/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * A bounded UTF-8 window over a file under a run directory.
 *
 * ``size`` is the whole file; ``content`` is the ``[offset, end)`` slice of
 * it that was actually read.  ``truncated`` says they differ, so a viewer
 * can page with ``since_offset=end`` rather than pretending it has the file.
 */
export type RunFileTextResponse = {
    content: string;
    end?: number;
    offset?: number;
    path: string;
    size: number;
    truncated?: boolean;
};

